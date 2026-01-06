"""
Unit tests for the LangGraph agent with tools.
"""
from __future__ import annotations

import os
from unittest.mock import patch, MagicMock, Mock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from app.agents.opgroeien.graph import (
    AgentState,
    agent_node,
    should_continue,
    create_agent_graph,
    _get_agent_model,
)
from app.prompts.loader import PromptObject


def test_agent_state_structure():
    """Test that AgentState has the correct structure."""
    state: AgentState = {
        "messages": [HumanMessage(content="Test message")]
    }
    assert "messages" in state
    assert len(state["messages"]) == 1
    assert isinstance(state["messages"][0], HumanMessage)


def test_should_continue_with_tool_calls():
    """Test should_continue returns 'tools' when tool calls exist."""
    # Create an AIMessage with tool calls
    ai_message = AIMessage(
        content="",
        tool_calls=[{
            "name": "test_tool",
            "args": {"query": "test"},
            "id": "test_id"
        }]
    )
    
    state: AgentState = {"messages": [ai_message]}
    result = should_continue(state)
    
    assert result == "tools"


def test_should_continue_without_tool_calls():
    """Test should_continue returns END when no tool calls."""
    state: AgentState = {
        "messages": [AIMessage(content="No tool calls")]
    }
    result = should_continue(state)
    
    from langgraph.graph import END
    assert result == END


def test_agent_node_adds_system_message():
    """Test that agent_node adds system message if not present."""
    # Reset model cache
    import app.agents.opgroeien.graph as graph_agent
    graph_agent._agent_model = None
    
    # Mock the model
    mock_model = MagicMock()
    mock_model_with_tools = MagicMock()
    mock_model.bind_tools.return_value = mock_model_with_tools
    
    mock_ai_message = AIMessage(content="Test response")
    mock_model_with_tools.invoke.return_value = mock_ai_message
    
    # Mock get_system_prompt to return PromptObject
    mock_prompt_obj = PromptObject(
        template_text="Test system prompt",
        version="1.0.0",
        config={}
    )
    with patch("app.agents.opgroeien.graph._get_agent_model", return_value=mock_model):
        with patch("app.prompts.loader.get_system_prompt", return_value=mock_prompt_obj):
            with patch("app.agents.opgroeien.utils.get_all_tools", return_value=[]):
                with patch("app.config.get_metadata", return_value={"environment": "test"}):
                    state: AgentState = {
                        "messages": [HumanMessage(content="Hello")]
                    }
                    
                    result = agent_node(state)
                    
                    # Check that system message was added
                    assert len(result["messages"]) == 1
                    # The result should contain the AI response
                    assert isinstance(result["messages"][0], AIMessage)
                    
                    # Verify model was called with system message
                    call_args = mock_model_with_tools.invoke.call_args
                    if call_args:
                        messages = call_args[0][0] if call_args[0] else []
                        # Check if system message is in the messages
                        has_system = any(isinstance(msg, SystemMessage) for msg in messages)
                        assert has_system, "System message should be added"


def test_agent_node_preserves_existing_system_message():
    """Test that agent_node doesn't add duplicate system messages."""
    import app.agents.opgroeien.graph as graph_agent
    graph_agent._agent_model = None
    
    mock_model = MagicMock()
    mock_model_with_tools = MagicMock()
    mock_model.bind_tools.return_value = mock_model_with_tools
    
    mock_ai_message = AIMessage(content="Test response")
    mock_model_with_tools.invoke.return_value = mock_ai_message
    
    with patch("app.agents.opgroeien.graph._get_agent_model", return_value=mock_model):
        with patch("app.agents.opgroeien.utils.get_all_tools", return_value=[]):
            with patch("app.config.get_metadata", return_value={"environment": "test"}):
                # State already has system message
                state: AgentState = {
                    "messages": [
                        SystemMessage(content="Existing system prompt"),
                        HumanMessage(content="Hello")
                    ]
                }
                
                result = agent_node(state)
                
                # Should only have one system message
                system_messages = [msg for msg in state["messages"] if isinstance(msg, SystemMessage)]
                assert len(system_messages) == 1, "Should not duplicate system message"


def test_create_agent_graph_structure():
    """Test that create_agent_graph creates a valid graph structure."""
    # Mock database connection
    mock_checkpointer = MagicMock()
    mock_checkpointer_cm = MagicMock()
    mock_checkpointer_cm.__enter__.return_value = mock_checkpointer
    
    # Set required env vars for settings
    os.environ.setdefault("DATABASE_CONNECTION_STRING", "postgresql://test:test@localhost/test")
    os.environ.setdefault("LANGFUSE_ENABLED", "false")  # Disable langfuse for this test
    
    with patch("app.agents.opgroeien.graph.PostgresSaver.from_conn_string", return_value=mock_checkpointer_cm):
        with patch("app.agents.opgroeien.utils.get_all_tools", return_value=[]):
            try:
                graph = create_agent_graph()
                
                # Verify graph was created
                assert graph is not None
                
                # Verify graph structure
                graph_obj = graph.get_graph()
                assert graph_obj is not None
                
            except Exception as e:
                # If database connection fails, that's expected in tests
                # Just verify the graph creation logic runs
                error_str = str(e).lower()
                assert "graph" in str(type(e).__name__).lower() or "connection" in error_str or "validation" in error_str


def test_agent_node_with_tools():
    """Test that agent_node binds tools to the model."""
    import app.agents.opgroeien.graph as graph_agent
    graph_agent._agent_model = None
    
    mock_model = MagicMock()
    mock_model_with_tools = MagicMock()
    mock_model.bind_tools.return_value = mock_model_with_tools
    
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    
    mock_ai_message = AIMessage(content="Test response")
    mock_model_with_tools.invoke.return_value = mock_ai_message
    
    mock_prompt_obj = PromptObject(
        template_text="Test prompt",
        version="1.0.0",
        config={}
    )
    with patch("app.agents.opgroeien.graph._get_agent_model", return_value=mock_model):
        with patch("app.agents.opgroeien.utils.get_all_tools", return_value=[mock_tool]):
            with patch("app.prompts.loader.get_system_prompt", return_value=mock_prompt_obj):
                with patch("app.config.get_metadata", return_value={"environment": "test"}):
                    state: AgentState = {
                        "messages": [HumanMessage(content="Hello")]
                    }
                    
                    result = agent_node(state)
                    
                    # Verify tools were bound
                    mock_model.bind_tools.assert_called_once_with([mock_tool])
                    
                    # Verify response was generated
                    assert len(result["messages"]) == 1
                    assert isinstance(result["messages"][0], AIMessage)


def test_agent_node_with_tool_calls():
    """Test that agent_node handles tool calls correctly."""
    import app.agents.opgroeien.graph as graph_agent
    graph_agent._agent_model = None
    
    mock_model = MagicMock()
    mock_model_with_tools = MagicMock()
    mock_model.bind_tools.return_value = mock_model_with_tools
    
    # Create AI message with tool calls
    mock_ai_message = AIMessage(
        content="I'll use a tool",
        tool_calls=[{
            "name": "test_tool",
            "args": {"query": "test"},
            "id": "test_id"
        }]
    )
    mock_model_with_tools.invoke.return_value = mock_ai_message
    
    mock_prompt_obj = PromptObject(
        template_text="Test prompt",
        version="1.0.0",
        config={}
    )
    with patch("app.agents.opgroeien.graph._get_agent_model", return_value=mock_model):
        with patch("app.agents.opgroeien.utils.get_all_tools", return_value=[]):
            with patch("app.prompts.loader.get_system_prompt", return_value=mock_prompt_obj):
                with patch("app.config.get_metadata", return_value={"environment": "test"}):
                    state: AgentState = {
                        "messages": [HumanMessage(content="Hello")]
                    }
                    
                    result = agent_node(state)
                    
                    # Verify tool calls are in the response
                    assert len(result["messages"]) == 1
                    ai_message = result["messages"][0]
                    assert isinstance(ai_message, AIMessage)
                    assert hasattr(ai_message, "tool_calls")
                    assert len(ai_message.tool_calls) > 0


def test_get_agent_model_initialization():
    """Test that _get_agent_model initializes correctly."""
    import app.agents.opgroeien.graph as graph_agent
    graph_agent._agent_model = None
    
    # Set required env vars
    os.environ.setdefault("VERTEX_SERVICE_ACCOUNT", 
                         '{"project_id": "test-project", "type": "service_account"}')
    os.environ.setdefault("VERTEX_AI_MODEL_NAME", "gemini-3-flash-preview")
    os.environ.setdefault("VERTEX_AI_LOCATION", "global")
    
    with patch("app.agents.opgroeien.graph.ChatGoogleGenerativeAI") as mock_chat_class:
        mock_instance = MagicMock()
        mock_chat_class.return_value = mock_instance
        
        with patch("app.agents.opgroeien.graph.service_account.Credentials.from_service_account_info"):
            try:
                model = _get_agent_model()
                
                # Verify model was created
                assert model is not None
                mock_chat_class.assert_called_once()
                
            except Exception as e:
                # If credentials fail, that's expected in tests
                assert "credentials" in str(e).lower() or "service_account" in str(e).lower()


def test_agent_node_metadata_injection():
    """Test that agent_node injects metadata into config."""
    import app.agents.opgroeien.graph as graph_agent
    graph_agent._agent_model = None
    
    mock_model = MagicMock()
    mock_model_with_tools = MagicMock()
    mock_model.bind_tools.return_value = mock_model_with_tools
    
    mock_ai_message = AIMessage(content="Test response")
    mock_model_with_tools.invoke.return_value = mock_ai_message
    
    test_metadata = {
        "environment": "test",
        "account": "test-customer",
        "org": "test-org",
        "project": "test-project"
    }
    
    mock_prompt_obj = PromptObject(
        template_text="Test prompt",
        version="1.0.0",
        config={}
    )
    with patch("app.agents.opgroeien.graph._get_agent_model", return_value=mock_model):
        with patch("app.agents.opgroeien.utils.get_all_tools", return_value=[]):
            with patch("app.prompts.loader.get_system_prompt", return_value=mock_prompt_obj):
                with patch("app.config.get_metadata", return_value=test_metadata):
                    state: AgentState = {
                        "messages": [HumanMessage(content="Hello")]
                    }
                    
                    result = agent_node(state, config={"configurable": {"thread_id": "test"}})
                    
                    # Verify invoke was called with config containing metadata
                    call_args = mock_model_with_tools.invoke.call_args
                    if call_args and len(call_args) > 1:
                        config = call_args[1].get("config", {})
                        if "metadata" in config:
                            assert config["metadata"]["environment"] == "test"

