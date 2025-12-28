"""
FastAPI application entrypoint.
"""
from __future__ import annotations

import json
import logging
import logging.config
import os
import queue
import threading
import uuid
import yaml
from pathlib import Path
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from firebase_admin.exceptions import FirebaseError
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from app.logging_utils import configure_structlog

# Initialize structlog before other imports that might use logging
configure_structlog()

# Parse Doppler secrets FIRST, before importing settings
# This ensures environment variables are set before Settings initialization
def parse_doppler_secrets() -> None:
    """Parse Doppler secrets JSON if provided (for Cloud Run)."""
    import sys
    
    # Get logger (structlog is already configured at this point)
    try:
        logger = structlog.get_logger(__name__)
    except Exception:
        # Fallback if logger not available yet
        logger = None
    
    doppler_secrets_json = os.getenv("DOPPLER_SECRETS_JSON")
    if not doppler_secrets_json:
        logger.warning("doppler_secrets_json_not_found", message="DOPPLER_SECRETS_JSON environment variable not set")
        print("WARNING: DOPPLER_SECRETS_JSON not found", file=sys.stderr)
        return
    
    try:
        secrets = json.loads(doppler_secrets_json)
        if logger:
            logger.info(
                "doppler_secrets_json_parsed",
                secret_count=len(secrets),
                secret_keys=list(secrets.keys()),
            )
        
        # Set individual environment variables from Doppler secrets
        set_count = 0
        skipped_count = 0
        for key, value in secrets.items():
            if key not in os.environ:  # Don't override existing env vars
                os.environ[key] = str(value)
                set_count += 1
            else:
                skipped_count += 1
                if logger:
                    logger.debug(
                        "env_var_already_set",
                        key=key,
                        message="Environment variable already set, skipping",
                    )
        
        if logger:
            logger.info(
                "doppler_secrets_loaded",
                secrets_set=set_count,
                secrets_skipped=skipped_count,
                has_database_connection_string="DATABASE_CONNECTION_STRING" in secrets,
                has_gcp_project="GCP_PROJECT" in secrets,
                has_vertex_service_account="VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM" in secrets,
            )
        
        # Verify critical secrets were set
        critical_keys = [
            "DATABASE_CONNECTION_STRING",
            "GCP_PROJECT",
            "GOOGLE_IDENTITY_PLATFORM_DOMAIN",
            "VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM",
        ]
        missing_critical = [key for key in critical_keys if key not in os.environ]
        if missing_critical:
            error_msg = f"Critical environment variables missing after parsing Doppler secrets: {', '.join(missing_critical)}"
            if logger:
                logger.error("critical_secrets_missing", missing_keys=missing_critical)
            print(f"ERROR: {error_msg}", file=sys.stderr)
            
    except json.JSONDecodeError as e:
        # Invalid JSON, log error
        error_msg = f"Failed to parse DOPPLER_SECRETS_JSON: {e}"
        if logger:
            logger.error(
                "doppler_secrets_json_invalid",
                error=str(e),
                error_type=type(e).__name__,
            )
        print(f"ERROR: {error_msg}", file=sys.stderr)
        raise
    except Exception as e:
        error_msg = f"Unexpected error parsing Doppler secrets: {e}"
        if logger:
            logger.exception("doppler_secrets_parse_error", error=str(e), error_type=type(e).__name__)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        raise

# Parse Doppler secrets at module level BEFORE importing settings
parse_doppler_secrets()

# Now import settings after secrets are parsed
from app.config import settings, get_metadata
from app.deps import verify_google_token
from app.graph import AgentState, create_graph, _get_langfuse_handler, get_checkpointer

# Enable debugpy for remote debugging if log_level is DEBUG
try:
    import debugpy
    if settings.log_level.upper() == "DEBUG":
        debugpy.listen(("0.0.0.0", 5678))
        logger = structlog.get_logger(__name__)
        logger.info("debugpy_listening", port=5678, log_level=settings.log_level)
except ImportError:
    pass  # debugpy not installed, skip
except Exception as e:
    logger = structlog.get_logger(__name__)
    logger.warning("debugpy_init_failed", error=str(e), log_level=settings.log_level)

# Load logging configuration from config.yaml
def setup_logging() -> None:
    """Setup logging from config.yaml."""
    config_file = Path(__file__).parent / "config.yaml"
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    with open(config_file) as f:
        config_data = yaml.safe_load(f)
        if config_data is None:
            config_data = {}
    
    env = "prd" if os.getenv("ENVIRONMENT") == "prd" else "dev"
    defaults = config_data.get("defaults", {})
    env_config = config_data.get(env, {})
    
    # Merge logging config (env overrides defaults)
    logging_config = defaults.get("logging", {})
    if "logging" in env_config:
        logging_config = {**logging_config, **env_config["logging"]}
    
    if logging_config:
        logging.config.dictConfig(logging_config)

# Setup logging at module level
setup_logging()

logger = structlog.get_logger(__name__)

# Log startup information (without sensitive values)
def log_startup_info() -> None:
    """Log startup information for debugging."""
    env_vars_to_check = [
        "ENVIRONMENT",
        "GCP_PROJECT",
        "GOOGLE_IDENTITY_PLATFORM_DOMAIN",
        "DATABASE_CONNECTION_STRING",
        "VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_BASE_URL",
        "DOPPLER_SECRETS_JSON",
    ]
    present_vars = {var: "SET" if os.getenv(var) else "MISSING" for var in env_vars_to_check}
    logger.info(
        "startup_env_check",
        environment_vars=present_vars,
    )

# Log startup info after logger is configured
try:
    log_startup_info()
except Exception as e:
    # If logging fails, at least print to stderr
    import sys
    print(f"WARNING: Failed to log startup info: {e}", file=sys.stderr)


def get_cors_headers(request: Request) -> dict[str, str]:
    """Get CORS headers for the given request."""
    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if origin and origin in settings.cors_allow_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


def extract_message_content(content: Any) -> str:
    """Extract message content, handling various formats."""
    if isinstance(content, list):
        # If content is a list (e.g., from multimodal responses), join or take first
        if content and isinstance(content[0], dict) and "text" in content[0]:
            return content[0]["text"]
        elif content and isinstance(content[0], str):
            return content[0]
        else:
            return str(content)
    elif not isinstance(content, str):
        return str(content)
    return content


def extract_ai_message(messages: list[BaseMessage]) -> BaseMessage:
    """Extract the last AI message from the message list."""
    ai_messages = [msg for msg in messages if not isinstance(msg, HumanMessage)]
    if not ai_messages:
        raise ValueError("No AI response generated")
    return ai_messages[-1]


# Initialize FastAPI app
app = FastAPI(title=settings.app_name, version=settings.app_version)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers to ensure CORS headers are included in error responses
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions and ensure CORS headers are included."""
    headers = dict(exc.headers) if exc.headers else {}
    headers.update(get_cors_headers(request))
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )


@app.exception_handler(FirebaseError)
async def firebase_exception_handler(request: Request, exc: FirebaseError):
    """Handle Firebase errors and ensure CORS headers are included."""
    logger.warning(
        "firebase_authentication_failed",
        error=str(exc),
        path=request.url.path,
        method=request.method,
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "Authentication failed"},
        headers=get_cors_headers(request),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all exceptions and ensure CORS headers are included."""
    logger.exception("Unhandled exception", exc_info=exc)
    
    # Determine error message based on exception type
    if isinstance(exc, ValueError):
        detail = str(exc)
    else:
        detail = "Internal server error"
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail},
        headers=get_cors_headers(request),
    )


# Lazy graph initialization - only create when needed
# This allows the app to start even if database connection fails initially
_graph: Any | None = None
_graph_lock = threading.Lock()

def get_graph() -> Any:
    """Get or create the graph instance (lazy initialization)."""
    global _graph
    if _graph is None:
        with _graph_lock:
            # Double-check pattern to avoid race conditions
            if _graph is None:
                try:
                    _graph = create_graph()
                    logger.info("graph_initialized_successfully")
                except Exception as e:
                    logger.error(
                        "graph_initialization_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise
    return _graph


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    user_id: str
    thread_id: str


@app.get("/health")
async def health_check():
    """Health check endpoint that doesn't require database or Firebase."""
    return {
        "status": "healthy",
        "service": "hit8-api",
        "version": settings.app_version,
    }


@app.get("/metadata")
async def get_metadata_endpoint(
    user_payload: dict = Depends(verify_google_token)
):
    """Get application metadata (customer, project, environment, log_level)."""
    try:
        metadata = get_metadata()
        # Add log_level to metadata
        metadata["log_level"] = settings.log_level
        return metadata
    except Exception as e:
        logger.error(
            "metadata_retrieval_failed",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metadata: {str(e)}"
        )


@app.get("/graph/structure")
async def get_graph_structure(
    user_payload: dict = Depends(verify_google_token)
):
    """Get the LangGraph structure as JSON."""
    try:
        logger.debug("graph_structure_export_starting")
        graph_obj = get_graph().get_graph()
        logger.debug("graph_get_graph_success", graph_type=type(graph_obj).__name__)
        
        # to_json() returns a dict, not a JSON string
        graph_structure = graph_obj.to_json()
        logger.debug(
            "graph_structure_export_success",
            structure_type=type(graph_structure).__name__,
            has_nodes="nodes" in graph_structure if isinstance(graph_structure, dict) else False,
        )
        return graph_structure
    except Exception as e:
        logger.exception(
            "graph_structure_export_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export graph structure: {str(e)}"
        )


@app.get("/graph/state")
async def get_graph_state(
    thread_id: str,
    user_payload: dict = Depends(verify_google_token)
):
    """Get the current execution state for a thread."""
    try:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        # Get state with history to track visited nodes
        # If thread doesn't exist, get_state returns None or empty state
        try:
            state = get_graph().get_state(config)
        except Exception as state_error:
            # If state retrieval fails, return empty state
            logger.debug(
                "graph_state_not_found",
                thread_id=thread_id,
                error=str(state_error),
                error_type=type(state_error).__name__,
            )
            return {
                "values": {},
                "next": [],
                "history": [],
            }
        
        # Debug: Log state object structure to understand what's available
        logger.debug(
            "graph_state_object_structure",
            thread_id=thread_id,
            has_next=hasattr(state, "next"),
            next_value=list(state.next) if hasattr(state, "next") and state.next else [],
            has_values=hasattr(state, "values"),
            has_tasks=hasattr(state, "tasks"),
            has_history=hasattr(state, "history"),
            has_checkpoint_id=hasattr(state, "checkpoint_id"),
            has_parent_checkpoint_id=hasattr(state, "parent_checkpoint_id"),
            has_metadata=hasattr(state, "metadata"),
            state_attrs=dir(state),
        )
        
        # Convert state to dict, handling serialization
        state_dict: dict[str, Any] = {
            "values": {},
            "next": state.next if hasattr(state, "next") else [],
        }
        
        # Serialize messages if present
        if hasattr(state, "values") and "messages" in state.values:
            # Convert messages to dict format
            messages = []
            for msg in state.values["messages"]:
                if hasattr(msg, "content"):
                    messages.append({
                        "type": type(msg).__name__,
                        "content": str(msg.content) if hasattr(msg, "content") else str(msg)
                    })
            state_dict["values"]["messages"] = messages
            state_dict["values"]["message_count"] = len(messages)
        
        # Add next nodes
        if hasattr(state, "next"):
            state_dict["next"] = list(state.next) if state.next else []
        
        # Get history by examining state and checkpoints
        # LangGraph execution history can be extracted from:
        # 1. State object metadata/tasks (if available)
        # 2. Fallback: infer from state values (if messages exist, "generate" executed)
        try:
            history: list[dict[str, Any]] = []
            
            # Method 1: Check if state has task information
            if hasattr(state, "tasks") and state.tasks:
                for task in state.tasks:
                    if hasattr(task, "name"):
                        history.append({"node": task.name})
                    elif isinstance(task, dict) and "name" in task:
                        history.append({"node": task["name"]})
            
            # Method 2: Fallback - infer from state values
            # If we have AI messages, the "generate" node must have executed
            # This is the most reliable method for our simple graph
            if not history:
                message_count = state_dict.get("values", {}).get("message_count", 0)
                if message_count > 0:
                    # Check if we have both human and AI messages (indicates generation happened)
                    messages = state_dict.get("values", {}).get("messages", [])
                    has_human = any(msg.get("type") == "HumanMessage" for msg in messages)
                    has_ai = any(msg.get("type") == "AIMessage" for msg in messages)
                    if has_human and has_ai:
                        # AI message exists, so "generate" node executed
                        history.append({"node": "generate"})
                        logger.debug(
                            "history_inferred_from_messages",
                            thread_id=thread_id,
                            message_count=message_count,
                            has_human=has_human,
                            has_ai=has_ai,
                        )
            
            state_dict["history"] = history
            
            logger.debug(
                "history_extracted",
                thread_id=thread_id,
                history_length=len(history),
                history_nodes=[h.get("node") for h in history if isinstance(h, dict)],
            )
            
        except Exception as e:
            logger.debug(
                "history_extraction_failed",
                error=str(e),
                error_type=type(e).__name__,
                thread_id=thread_id,
            )
            state_dict["history"] = []
        
        logger.debug(
            "graph_state_retrieved",
            thread_id=thread_id,
            next_nodes=state_dict["next"],
            history_length=len(state_dict.get("history", [])),
        )
        
        return state_dict
    except Exception as e:
        logger.error(
            "graph_state_retrieval_failed",
            error=str(e),
            error_type=type(e).__name__,
            thread_id=thread_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve graph state: {str(e)}"
        )


async def _stream_chat_events(
    request: ChatRequest,
    user_id: str,
    thread_id: str,
    initial_state: AgentState,
    config: dict[str, Any],
    langfuse_handler: Any | None,
    centralized_metadata: dict[str, str],
):
    """Stream chat execution events using LangGraph stream_events (sync version for PostgresSaver compatibility)."""
    import asyncio
    
    final_response: str | None = None
    
    try:
        # Use stream (sync) instead of async methods because
        # PostgresSaver doesn't fully support async checkpoint operations (aget_tuple raises NotImplementedError)
        # Run sync stream in a background thread to avoid blocking
        event_queue: queue.Queue = queue.Queue()
        stream_done = threading.Event()
        stream_error: Exception | None = None
        
        def run_stream():
            """Run sync stream in a thread and put state chunks in queue."""
            nonlocal stream_error
            try:
                # Send graph start event
                event_queue.put(("__event__", {"type": "graph_start", "thread_id": thread_id}))
                # Send node start event
                event_queue.put(("__event__", {"type": "node_start", "node": "generate", "thread_id": thread_id}))
                
                # Stream the graph execution (sync)
                for chunk in get_graph().stream(initial_state, config=config):
                    event_queue.put(("__chunk__", chunk))
                
                # Send node end event
                event_queue.put(("__event__", {"type": "node_end", "node": "generate", "thread_id": thread_id}))
            except Exception as e:
                stream_error = e
                event_queue.put(("__error__", e))
            finally:
                stream_done.set()
        
        # Start streaming in background thread
        stream_thread = threading.Thread(target=run_stream, daemon=True)
        stream_thread.start()
        
        # Yield events and process chunks as they arrive from the queue
        while not stream_done.is_set() or not event_queue.empty():
            try:
                # Wait for event/chunk with timeout
                item = event_queue.get(timeout=0.1)
                item_type, item_data = item
                
                if item_type == "__error__":
                    raise item_data
                elif item_type == "__event__":
                    # Send event to client
                    yield f"data: {json.dumps(item_data)}\n\n"
                elif item_type == "__chunk__":
                    # Process state chunk
                    chunk = item_data
                    if "messages" in chunk and chunk["messages"]:
                        # Get the last message (should be AI response)
                        last_message = chunk["messages"][-1]
                        if hasattr(last_message, "content") and not isinstance(last_message, HumanMessage):
                            # This is the AI response
                            final_response = extract_message_content(last_message.content)
            except queue.Empty:
                # No item yet, continue waiting
                await asyncio.sleep(0.01)
                continue
            except Exception as e:
                # Error from stream thread
                raise
        
        # Wait for thread to complete
        stream_thread.join(timeout=5.0)
        
        # Check for errors
        if stream_error:
            raise stream_error
        
        # Get final state and send graph end event
        final_state = get_graph().get_state(config)
        if hasattr(final_state, "values") and "messages" in final_state.values:
            ai_message = extract_ai_message(final_state.values["messages"])
            final_response = extract_message_content(ai_message.content)
            
            logger.debug(
                "graph_end_event",
                thread_id=thread_id,
                response_length=len(final_response) if final_response else 0,
            )
            
            # Send final state update
            state_data = {
                "type": "graph_end",
                "thread_id": thread_id,
                "response": final_response,
            }
            yield f"data: {json.dumps(state_data)}\n\n"
        
        # Ensure we send the final response even if graph_end event wasn't caught
        if not final_response:
            logger.warning(
                "graph_end_not_received",
                thread_id=thread_id,
            )
            # Try to get the final state one more time
            try:
                final_state = get_graph().get_state(config)
                if hasattr(final_state, "values") and "messages" in final_state.values:
                    ai_message = extract_ai_message(final_state.values["messages"])
                    final_response = extract_message_content(ai_message.content)
                    
                    logger.debug(
                        "graph_end_fallback",
                        thread_id=thread_id,
                        response_length=len(final_response) if final_response else 0,
                    )
                    
                    state_data = {
                        "type": "graph_end",
                        "thread_id": thread_id,
                        "response": final_response,
                    }
                    yield f"data: {json.dumps(state_data)}\n\n"
            except Exception as e:
                logger.error(
                    "failed_to_get_final_state",
                    error=str(e),
                    thread_id=thread_id,
                )
        
        # Flush Langfuse traces after streaming completes
        if langfuse_handler and settings.langfuse_enabled:
            try:
                from langfuse import get_client
                langfuse_client = get_client()
                environment = centralized_metadata["environment"]
                if environment == "prd":
                    langfuse_client.shutdown()
                else:
                    langfuse_client.flush()
            except Exception as e:
                logger.error(
                    "langfuse_flush_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    environment=centralized_metadata["environment"],
                )
        
    except Exception as e:
        # Get detailed error information
        error_type = type(e).__name__
        error_str = str(e) if str(e) else ""
        error_message = error_str if error_str else f"{error_type}: An error occurred during streaming"
        
        # Log full exception details for debugging
        logger.exception(
            "streaming_error",
            error=error_message,
            error_type=error_type,
            error_repr=repr(e),
            thread_id=thread_id,
            exc_info=True,
        )
        
        error_data = {
            "type": "error",
            "error": error_message,
            "error_type": error_type,
            "thread_id": thread_id,
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@app.post("/chat")
async def chat(
    request: ChatRequest,
    user_payload: dict = Depends(verify_google_token)
):
    """Chat endpoint that processes user messages through LangGraph with streaming support."""
    user_id = user_payload["sub"]
    
    # Use provided thread_id or generate one for state tracking
    # Frontend generates thread_id to enable immediate polling
    thread_id = request.thread_id if request.thread_id else str(uuid.uuid4())
    
    initial_state: AgentState = {
        "messages": [HumanMessage(content=request.message)]
    }
    
    # Get Langfuse callback handler if enabled
    langfuse_handler = _get_langfuse_handler()
    
    # Prepare config with callbacks, metadata, and thread_id
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id}
    }
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        logger.debug(
            "langfuse_callback_handler_added",
            handler_type=type(langfuse_handler).__name__,
            thread_id=thread_id,
        )
    
    # Add metadata for Langfuse tracing using centralized metadata
    centralized_metadata = get_metadata()
    metadata: dict[str, Any] = {
        "langfuse_user_id": user_id,
        **centralized_metadata,  # Includes environment, customer, project
    }
    logger.debug(
        "langfuse_metadata_constructed",
        environment=centralized_metadata["environment"],
        customer=centralized_metadata["customer"],
        project=centralized_metadata["project"],
        thread_id=thread_id,
    )
    
    config["metadata"] = metadata
    
    # Log start of execution
    logger.debug(
        "graph_execution_started",
        thread_id=thread_id,
        message_length=len(request.message),
    )
    
    # Return streaming response with Server-Sent Events
    return StreamingResponse(
        _stream_chat_events(
            request=request,
            user_id=user_id,
            thread_id=thread_id,
            initial_state=initial_state,
            config=config,
            langfuse_handler=langfuse_handler,
            centralized_metadata=centralized_metadata,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )

