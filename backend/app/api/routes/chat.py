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
from app.api.streaming import (
    create_stream_thread,
    extract_final_response,
    process_stream_queue,
)
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
    """Stream chat execution events using LangGraph stream_events().
    
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
    final_response: str | None = None
    
    try:
        # Run stream_events() in a background thread to avoid blocking
        event_queue: queue.Queue = queue.Queue()
        stream_done = threading.Event()
        
        # Create and start unified streaming thread
        stream_threads, stream_errors = create_stream_thread(
            initial_state, config, thread_id, event_queue, stream_done, org, project
        )
        
        # Process events and chunks from queue
        final_response_ref: list[str | None] = [None]
        async for event_str in process_stream_queue(event_queue, stream_done, final_response_ref, thread_id):
            yield event_str
        
        # Wait for thread to complete
        for thread in stream_threads:
            thread.join(timeout=30.0)        
        
        # Check for errors
        stream_error = stream_errors[0][0] if len(stream_errors) > 0 and stream_errors[0] else None
        
        if stream_error:
            logger.error(
                "stream_error",
                error=str(stream_error),
                error_type=type(stream_error).__name__,
                thread_id=thread_id,
            )
            # Don't raise - we've already sent error event, now send graph_end to complete stream
        
        # Get final response - prefer from queue, then from final state extraction
        if final_response_ref[0]:
            final_response = final_response_ref[0]
        else:
            # Try to get final state
            final_response = extract_final_response(config, thread_id, org, project)
        
        # If still no response, try one more time to get final state
        if not final_response:
            final_response = extract_final_response(config, thread_id, org, project)
        
        # Always send graph_end event (even if response is empty, to signal completion)
        logger.debug(
            "graph_end_event",
            thread_id=thread_id,
            response_length=len(final_response) if final_response else 0,
            has_response=bool(final_response),
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
            "type": EVENT_ERROR,
            "error": error_message,
            "error_type": error_type,
            "thread_id": thread_id,
        }
        yield f"data: {json.dumps(error_data)}\n\n"


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
        message = f"{message}\n\n---\n\nUploaded Documents:\n{document_content}"
    
    # Initialize system prompt for the configured agent type
    system_prompt_obj = get_system_prompt(settings.FLOW)
    system_prompt = system_prompt_obj.render()
    
    initial_state: AgentState = {
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=message)
        ]
    }
    
    # Get Langfuse callback handler if enabled
    langfuse_handler = get_langfuse_handler()
    
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
        thread_id=thread_id,
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

