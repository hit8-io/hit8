"""
Chat endpoint with streaming support.
"""
from __future__ import annotations

import json
import queue
import threading
import uuid
from typing import TYPE_CHECKING, Any

import structlog

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage

from app.flows.common import get_langfuse_handler
from app.flows.opgroeien.poc.chat.graph import AgentState
from app.api.constants import EVENT_ERROR, EVENT_GRAPH_END
from app.api.file_processing import process_uploaded_files
from app.api.streaming.async_events import process_async_stream_events
from app.api.streaming.finalize import extract_final_response
from app.api.graph_manager import get_graph
from app.api.user_threads import upsert_thread, generate_thread_title, thread_exists
from app.config import settings
from app.auth import verify_google_token
from app.prompts.loader import get_system_prompt
from app.user_config import validate_user_access
import importlib

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler

logger = structlog.get_logger(__name__)
router = APIRouter()


async def stream_chat_events(
    message: str,
    user_id: str,
    thread_id: str,
    initial_state: AgentState,
    config: dict[str, Any],
    langfuse_handler: CallbackHandler | None,
    centralized_metadata: dict[str, str],
    org: str,
    project: str,
):
    """Stream chat execution events using LangGraph astream_events() directly.
    
    Pure async implementation - runs entirely in the FastAPI event loop,
    eliminating the need for background threads and event loop synchronization.
    
    Args:
        message: User message content
        user_id: User identifier
        thread_id: Thread identifier
        initial_state: Initial agent state
        config: Graph configuration
        langfuse_handler: Langfuse callback handler
        centralized_metadata: Centralized metadata dict
        
    Yields:
        Server-Sent Event strings
    """
    from app.api.streaming.async_events import process_async_stream_events
    
    final_response: str | None = None
    
    try:
        # Set thread_id in observability context
        try:
            from app.api.observability import _current_thread_id, initialize_execution
            _current_thread_id.set(thread_id)
            initialize_execution(thread_id)
        except Exception:
            # Don't fail if observability is not available
            pass
        
        logger.info(
            "stream_started",
            thread_id=thread_id,
            initial_message_count=len(initial_state.get("messages", [])),
        )
        
        # Get graph (uses checkpointer initialized in main event loop)
        graph = get_graph(org, project)
        
        # Process events directly from astream_events - runs in main event loop
        # This ensures checkpointer operations work correctly (no event loop issues)
        # Use mutable dict to track accumulated content
        accumulated_content_ref: dict[str, str] = {"content": ""}
        
        async for event_str in process_async_stream_events(
            graph, initial_state, config, thread_id, org, project, accumulated_content_ref, flow="chat"
        ):
            yield event_str
        
        # Get final response from accumulated content reference
        final_response = accumulated_content_ref.get("content", "")
        if not final_response:
            final_response = extract_final_response(config, thread_id, org, project)
        
        # Always send graph_end event (even if response is empty, to signal completion)
        logger.debug(
            "graph_end_event",
            thread_id=thread_id,
            response_length=len(final_response) if final_response else 0,
            has_response=bool(final_response),
        )
        
        # Flush Langfuse traces to ensure they're sent
        if langfuse_handler:
            try:
                from app.flows.common import get_langfuse_client
                langfuse_client = get_langfuse_client()
                if langfuse_client:
                    langfuse_client.flush()
                    logger.debug("langfuse_traces_flushed", thread_id=thread_id)
            except Exception as e:
                logger.warning(
                    "langfuse_flush_failed",
                    error=str(e),
                    error_type=type(e).__name__,
                    thread_id=thread_id,
                )
        
        state_data = {
            "type": EVENT_GRAPH_END,
            "thread_id": thread_id,
            "response": final_response or "",
        }
        yield f"data: {json.dumps(state_data)}\n\n"
        
    except Exception as e:
        # Get detailed error information
        error_type = type(e).__name__
        error_str = str(e) if str(e) else ""
        error_message = error_str if error_str else f"{error_type}: An error occurred during streaming"
        
        # Check if this is a connection error (Ollama, database, etc.)
        is_connection_error = (
            "Connection refused" in error_str or
            "Errno 111" in error_str or
            "ConnectError" in error_type or
            "ConnectionError" in error_type
        )
        
        # Log full exception details for debugging
        logger.exception(
            "streaming_error",
            error=error_message,
            error_type=error_type,
            error_repr=repr(e),
            thread_id=thread_id,
            is_connection_error=is_connection_error,
            org=org,
            project=project,
            exc_info=True,
        )
        
        error_data = {
            "type": EVENT_ERROR,
            "error": error_message,
            "error_type": error_type,
            "thread_id": thread_id,
        }
        yield f"data: {json.dumps(error_data)}\n\n"
    finally:
        # Finalize execution metrics tracking
        try:
            from app.api.observability import finalize_execution
            finalize_execution(thread_id)
        except Exception:
            # Don't fail if observability is not available
            pass


@router.post("")
async def chat(
    message: str = Form(...),
    thread_id: str | None = Form(None),
    files: list[UploadFile] = File(None),
    user_payload: dict = Depends(verify_google_token),
    x_org: str = Header(..., alias="X-Org"),
    x_project: str = Header(..., alias="X-Project"),
):
    """Chat endpoint that processes user messages through LangGraph with streaming support.
    
    Accepts multipart/form-data with message, optional thread_id, and optional files.
    Requires X-Org and X-Project headers to specify which org/project to use.
    """
    user_id = user_payload["sub"]
    email = user_payload["email"]
    org = x_org.strip()
    project = x_project.strip()
    
    # Use provided thread_id or generate one for state tracking
    session_id = thread_id if thread_id else str(uuid.uuid4())
    
    # Generate title for new threads (threads that don't exist in database yet)
    # Also generate title for existing threads that don't have a title yet
    thread_title: str | None = None
    try:
        thread_already_exists = await thread_exists(session_id)
        if not thread_already_exists:
            # New thread - generate title from first message
            thread_title = generate_thread_title(message)
            logger.info(
                "thread_title_generated_for_new_thread",
                thread_id=session_id,
                has_title=thread_title is not None,
                title_preview=thread_title[:50] if thread_title else None,
            )
        else:
            # Thread exists - check if it needs a title
            # We'll let upsert_thread handle setting title if current title is NULL
            thread_title = generate_thread_title(message)
            logger.debug(
                "thread_title_generated_for_existing_thread",
                thread_id=session_id,
                has_title=thread_title is not None,
            )
    except Exception as e:
        # Log error but don't fail the request if title generation/check fails
        logger.warning(
            "thread_title_generation_failed",
            thread_id=session_id,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True,
        )
    
    # Derive flow identifier: "{org}.{project}.chat"
    flow_identifier = f"{org}.{project}.chat"
    
    # Track thread in database (non-blocking - errors are logged but don't fail the request)
    # Uses upsert to handle both new threads (create) and existing threads (update last_accessed_at)
    try:
        await upsert_thread(session_id, user_id, title=thread_title, flow=flow_identifier)
    except Exception as e:
        # Log error but don't fail the request if thread tracking fails
        logger.warning(
            "thread_tracking_failed",
            thread_id=session_id,
            user_id=user_id,
            flow=flow_identifier,
            error=str(e),
            error_type=type(e).__name__,
        )
    
    # Validate user has access to the requested org/project
    if not validate_user_access(email, org, project):
        logger.warning(
            "user_access_denied",
            email=email,
            org=org,
            project=project,
            thread_id=session_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User does not have access to org '{org}' / project '{project}'",
        )
    
    # Process uploaded files and append converted content to message
    document_content = await process_uploaded_files(files or [], session_id)
    if document_content:
        # Truncate document content to prevent token limit issues
        MAX_DOCUMENT_CONTENT_LENGTH = 50_000  # Max characters for uploaded documents
        if len(document_content) > MAX_DOCUMENT_CONTENT_LENGTH:
            truncated = document_content[:MAX_DOCUMENT_CONTENT_LENGTH]
            # Try to cut at a section boundary
            last_section = truncated.rfind('\n\n---\n\n')
            if last_section > MAX_DOCUMENT_CONTENT_LENGTH * 0.8:
                truncated = document_content[:last_section]
            else:
                # Cut at newline if possible
                last_newline = truncated.rfind('\n\n')
                if last_newline > MAX_DOCUMENT_CONTENT_LENGTH * 0.9:
                    truncated = document_content[:last_newline]
            document_content = truncated + f"\n\n[Document content truncated: showing first {len(truncated):,} of {len(document_content):,} characters]"
        message = f"{message}\n\n---\n\nUploaded Documents:\n{document_content}"
    
    # Initialize system prompt for the configured agent type
    system_prompt_obj = get_system_prompt(settings.FLOW)
    system_prompt = system_prompt_obj.render()
    
    # Always include SystemMessage in initial_state
    # LangGraph will handle merging with checkpointed state if thread exists
    # The windowing in agent_node will ensure only recent messages are kept
    initial_state: AgentState = {
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=message)
        ]
    }
    
    # Get Langfuse callback handler if enabled
    langfuse_handler = get_langfuse_handler()
    
    # Prepare config with callbacks, metadata, and thread_id
    # Use session_id (the actual thread_id being used) not the form parameter
    config: dict[str, Any] = {
        "configurable": {"thread_id": session_id}
    }
    if langfuse_handler:
        config["callbacks"] = [langfuse_handler]
        logger.debug(
            "langfuse_callback_handler_added",
            handler_type=type(langfuse_handler).__name__,
            thread_id=session_id,
        )
    
    # Build metadata: environment and account from settings, org/project from headers
    centralized_metadata = settings.metadata
    metadata: dict[str, Any] = {
        "langfuse_user_id": user_id,
        **centralized_metadata,  # Includes environment, account
        "org": org,
        "project": project,
    }
    logger.debug(
        "langfuse_metadata_constructed",
        environment=centralized_metadata["environment"],
        account=centralized_metadata["account"],
        org=org,
        project=project,
        thread_id=session_id,
    )
    
    config["metadata"] = metadata
    
    # Log start of execution
    logger.debug(
        "graph_execution_started",
        thread_id=session_id,
        message_length=len(message),
        file_count=len(files) if files else 0,
        org=org,
        project=project,
    )
    
    # Return streaming response with Server-Sent Events
    return StreamingResponse(
        stream_chat_events(
            message=message,
            user_id=user_id,
            thread_id=session_id,
            initial_state=initial_state,
            config=config,
            langfuse_handler=langfuse_handler,
            centralized_metadata=centralized_metadata,
            org=org,
            project=project,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )

