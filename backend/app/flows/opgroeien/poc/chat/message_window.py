"""
Message windowing utilities to prevent token limit issues.

Implements sliding window approach to keep conversation history manageable
while preserving recent context and tool call/response pairs.
"""
from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app import constants

logger = structlog.get_logger(__name__)


def truncate_tool_result(content: str, max_length: int | None = None) -> str:
    """
    Truncate tool result content if it exceeds max_length.
    
    Args:
        content: Tool result content to truncate
        max_length: Maximum allowed length (defaults to CONSTANTS["MAX_TOOL_RESULT_LENGTH"])
        
    Returns:
        Truncated content with truncation notice if needed
    """
    if max_length is None:
        max_length = constants.CONSTANTS["MAX_TOOL_RESULT_LENGTH"]
    if len(content) <= max_length:
        return content
    
    # Try to cut at a newline or space to avoid cutting words
    truncated = content[:max_length]
    last_newline = truncated.rfind('\n')
    last_space = truncated.rfind(' ')
    
    # Prefer cutting at newline, then space, then hard cut
    cut_point = max_length
    if last_newline > max_length * 0.9:
        cut_point = last_newline
    elif last_space > max_length * 0.9:
        cut_point = last_space
    
    truncated = content[:cut_point].rstrip()
    truncated += f"\n\n[Content truncated: showing first {len(truncated):,} of {len(content):,} characters]"
    
    return truncated


def window_messages(
    messages: list[BaseMessage],
    max_pairs: int | None = None,
    max_tool_result_length: int | None = None,
) -> list[BaseMessage]:
    """
    Apply sliding window to messages to prevent token limit issues.
    
    Strategy:
    1. Always keep SystemMessage (first message)
    2. Keep the most recent N Human/AI message pairs
    3. For each kept AI message with tool calls, keep its corresponding ToolMessages
    4. Truncate large tool results
    
    Args:
        messages: Full list of messages from state
        max_pairs: Maximum number of recent Human/AI pairs to keep (defaults to CONSTANTS["MAX_RECENT_MESSAGE_PAIRS"])
        max_tool_result_length: Maximum length for tool result content (defaults to CONSTANTS["MAX_TOOL_RESULT_LENGTH"])
        
    Returns:
        Windowed list of messages
    """
    if max_pairs is None:
        max_pairs = constants.CONSTANTS["MAX_RECENT_MESSAGE_PAIRS"]
    if max_tool_result_length is None:
        max_tool_result_length = constants.CONSTANTS["MAX_TOOL_RESULT_LENGTH"]
    
    if len(messages) == 0:
        return messages
    
    # Separate system messages (should be at the start)
    # Keep only the first SystemMessage to avoid duplicates
    system_messages: list[BaseMessage] = []
    other_messages: list[BaseMessage] = []
    system_message_found = False
    
    for msg in messages:
        if isinstance(msg, SystemMessage):
            # Only keep the first SystemMessage to avoid duplicates from merging
            if not system_message_found:
                system_messages.append(msg)
                system_message_found = True
            # Skip duplicate SystemMessages
        else:
            other_messages.append(msg)
    
    # If no other messages, just return system messages
    if not other_messages:
        return system_messages
    
    # Group messages into conversation turns
    # Message order: HumanMessage -> AIMessage (with tool_calls) -> ToolMessages -> AIMessage (final) -> next HumanMessage...
    turns: list[list[BaseMessage]] = []
    current_turn: list[BaseMessage] = []
    
    for msg in other_messages:
        if isinstance(msg, HumanMessage):
            # Start a new turn
            if current_turn:
                turns.append(current_turn)
            current_turn = [msg]
        elif isinstance(msg, AIMessage):
            # Add AI message to current turn
            current_turn.append(msg)
        elif isinstance(msg, ToolMessage):
            # Add tool message to current turn (truncate if needed)
            if len(msg.content) > max_tool_result_length:
                truncated_content = truncate_tool_result(msg.content, max_tool_result_length)
                # Create new ToolMessage with truncated content
                truncated_msg = ToolMessage(
                    content=truncated_content,
                    tool_call_id=msg.tool_call_id,
                    name=getattr(msg, "name", None),
                )
                current_turn.append(truncated_msg)
            else:
                current_turn.append(msg)
        else:
            # Unknown message type - add to current turn
            current_turn.append(msg)
    
    # Add last turn if exists
    if current_turn:
        turns.append(current_turn)
    
    # Take only the most recent N turns
    recent_turns = turns[-max_pairs:] if len(turns) > max_pairs else turns
    
    # Reconstruct windowed messages
    windowed: list[BaseMessage] = system_messages.copy()
    
    for turn in recent_turns:
        windowed.extend(turn)
    
    original_count = len(messages)
    windowed_count = len(windowed)
    
    if original_count != windowed_count:
        logger.info(
            "messages_windowed",
            original_count=original_count,
            windowed_count=windowed_count,
            removed_count=original_count - windowed_count,
            max_pairs=max_pairs,
            turns_kept=len(recent_turns),
            total_turns=len(turns),
        )
    
    return windowed
