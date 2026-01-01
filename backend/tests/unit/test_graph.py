"""
Unit tests for LangGraph logic.
"""
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from app.agents.simple.graph import generate_node, AgentState, _get_model


def test_generate_node_adds_response():
    """Test that generate_node adds AI response to state."""
    # Reset the model cache
    import app.agents.simple.graph as simple_graph
    simple_graph._model = None
    
    # Setup: Mock the model getter
    mock_model = MagicMock()
    mock_ai_message = AIMessage(content="Mocked AI Response")
    mock_model.invoke.return_value = mock_ai_message
    
    with patch("app.agents.simple.graph._get_model", return_value=mock_model):
        # Setup: Initial state
        state: AgentState = {"messages": [HumanMessage(content="Hi")]}
        
        # Action: Run the node
        new_state = generate_node(state)
        
        # Assert: Did we get a response?
        assert len(new_state["messages"]) == 2
        assert new_state["messages"][-1].content == "Mocked AI Response"
        assert isinstance(new_state["messages"][-1], AIMessage)

