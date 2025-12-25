"""
Unit tests for LangGraph logic.
"""
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from app.graph import generate_node, AgentState


def test_generate_node_adds_response():
    """Test that generate_node adds AI response to state."""
    # Setup: Mock both credentials and the Google Chat Model
    with patch("app.graph.service_account.Credentials.from_service_account_info") as MockCreds, \
         patch("app.graph.ChatGoogleGenerativeAI") as MockModel:
        # Configure the mock credentials
        MockCreds.return_value = MagicMock()
        
        # Configure the mock to return a fake message
        mock_instance = MockModel.return_value
        mock_ai_message = AIMessage(content="Mocked AI Response")
        mock_instance.invoke.return_value = mock_ai_message
        
        # Setup: Initial state
        state: AgentState = {"messages": [HumanMessage(content="Hi")]}
        
        # Action: Run the node
        new_state = generate_node(state)
        
        # Assert: Did we get a response?
        assert len(new_state["messages"]) == 2
        assert new_state["messages"][-1].content == "Mocked AI Response"
        assert isinstance(new_state["messages"][-1], AIMessage)

