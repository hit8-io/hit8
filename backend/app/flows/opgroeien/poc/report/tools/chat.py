"""
Bridge tool to consult the general knowledge base (Chat Graph).
"""
import uuid
from typing import Optional

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from app.api.observability import _current_model_name
from app.flows.common import get_consult_llm_semaphore, execute_llm_call_async
from app.flows.opgroeien.poc.chat.graph import create_agent_graph
from app.api.utils import extract_message_content

logger = structlog.get_logger(__name__)

# Global cache for the compiled graph
_CACHED_CHAT_GRAPH = None

def _get_chat_graph():
    global _CACHED_CHAT_GRAPH
    if _CACHED_CHAT_GRAPH is None:
        _CACHED_CHAT_GRAPH = create_agent_graph()
    return _CACHED_CHAT_GRAPH

@tool
async def consult_general_knowledge(query: str) -> str:
    """
    Consults the general knowledge base to answer questions about regulations, 
    context, or definitions that are not found in the procedure file itself.
    
    Args:
        query: A specific question, e.g., "What is the legal retention period for medical records in PGJO?"
        
    Returns:
        The answer from the general knowledge agent.
    """
    try:
        chat_app = _get_chat_graph()
        
        # Validate query before creating message
        if not query or not query.strip():
            logger.error(
                "consult_general_knowledge_empty_query",
                query=query,
            )
            return "Error: Query cannot be empty."
        
        # 1. Create a minimal input state
        input_state = {"messages": [HumanMessage(content=query)]}
        
        # 2. Use a specific sub-thread ID to keep report queries isolated 
        # from the user's main chat history. Forward model_name from parent (e.g. report
        # analyst) so the nested chat uses the same model and observability shows one model.
        sub_thread_id = f"sys-consult-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": sub_thread_id}}
        parent_model = _current_model_name.get()
        if parent_model:
            config["configurable"]["model_name"] = parent_model

        # 3. Invoke the Chat Graph with flow control
        # Set _current_model_name before ainvoke so nested chat's agent_node can read it
        # (LangGraph may not pass config to nodes when invoked from tools)
        consult_tok = None
        if parent_model:
            consult_tok = _current_model_name.set(parent_model)
        try:
            # Get provider from model config if parent_model is available
            provider = None
            if parent_model:
                from app.flows.common import get_provider_for_model
                provider = get_provider_for_model(model_name=parent_model)
            
            # Prepare call context for logging
            call_context = {
                "node": "consult_general_knowledge",
                "flow": "report",
                "query": query[:100] if query else None,  # Truncate for logging
            }
            if parent_model:
                call_context["model_name"] = parent_model
            if provider:
                call_context["provider"] = provider
            
            # Helper coroutine for graph invocation
            async def _consult_graph_call():
                """Execute nested chat graph invocation."""
                logger.info(
                    "consult_general_knowledge_nested_call_starting",
                    query=query[:100] if query else None,
                    parent_model=parent_model,
                    provider=provider,
                )
                result = await chat_app.ainvoke(input_state, config=config)
                logger.info(
                    "consult_general_knowledge_nested_call_completed",
                    query=query[:100] if query else None,
                    parent_model=parent_model,
                    provider=provider,
                )
                return result
            
            # Use generic wrapper with consult-specific semaphore
            logger.info(
                "consult_general_knowledge_wrapper_starting",
                query=query[:100] if query else None,
                parent_model=parent_model,
                provider=provider,
            )
            result = await execute_llm_call_async(
                _consult_graph_call,
                semaphore=get_consult_llm_semaphore(),
                call_context=call_context,
            )
            logger.info(
                "consult_general_knowledge_wrapper_completed",
                query=query[:100] if query else None,
                parent_model=parent_model,
                provider=provider,
            )
        finally:
            if consult_tok is not None:
                _current_model_name.reset(consult_tok)
        
        # 4. Return the AI's final answer
        # Extract content using utility function to handle structured formats (e.g., Gemini signatures)
        if result and "messages" in result and result["messages"]:
            raw_content = result["messages"][-1].content
            return extract_message_content(raw_content)
        return "No answer received."
        
    except Exception as e:
        return f"Error querying general knowledge: {str(e)}"
