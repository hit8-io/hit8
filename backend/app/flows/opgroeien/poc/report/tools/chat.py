"""
Bridge tool to consult the general knowledge base (Chat Graph).
"""
import uuid
from typing import Optional

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

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
        # from the user's main chat history.
        sub_thread_id = f"sys-consult-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": sub_thread_id}}
        
        # 3. Invoke the Chat Graph
        result = await chat_app.ainvoke(input_state, config=config)
        
        # 4. Return the AI's final answer
        # Extract content using utility function to handle structured formats (e.g., Gemini signatures)
        if result and "messages" in result and result["messages"]:
            raw_content = result["messages"][-1].content
            return extract_message_content(raw_content)
        return "No answer received."
        
    except Exception as e:
        return f"Error querying general knowledge: {str(e)}"
