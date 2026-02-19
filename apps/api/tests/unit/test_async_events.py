"""
Unit tests for async_events.py refactored functions.
"""
from __future__ import annotations

import os
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest

# Set required env vars before importing app modules (which import settings)
os.environ.setdefault("GCP_PROJECT", "test-project")
os.environ.setdefault("DATABASE_CONNECTION_STRING", "postgresql://test:test@localhost/test")
os.environ.setdefault("GOOGLE_IDENTITY_PLATFORM_DOMAIN", "test-domain")
os.environ.setdefault("API_TOKEN", "test-token")
os.environ.setdefault("VERTEX_SERVICE_ACCOUNT", '{"project_id": "test", "type": "service_account"}')
os.environ.setdefault("BRIGHTDATA_API_KEY", "test-key")
os.environ.setdefault("ENVIRONMENT", "dev")

from app.api.streaming.async_events import (
    NodeEventResult,
    StreamState,
    SNAPSHOT_THROTTLE_INTERVAL,
    LONG_RUNNING_TASK_THRESHOLD,
    DEFAULT_PREVIEW_LENGTH,
    CHAPTER_PREVIEW_LENGTH,
    TOOL_RESULT_PREVIEW_LENGTH,
    _extract_run_id,
    _create_envelope_event,
    _should_emit_throttled_snapshot,
    _initialize_stream_state,
    _process_tool_event_async,
    _process_node_event_async,
)
from app.api.streaming.llm import (
    extract_chunk_content,
    process_chat_model_stream_event,
)
from app.api.streaming.policy import FlowPolicy


class TestConstants:
    """Test that constants are properly defined."""
    
    def test_constants_defined(self):
        """Test that all constants are defined with expected values."""
        assert SNAPSHOT_THROTTLE_INTERVAL == 12.0
        assert LONG_RUNNING_TASK_THRESHOLD == 20.0
        assert DEFAULT_PREVIEW_LENGTH == 150
        assert CHAPTER_PREVIEW_LENGTH == 200
        assert TOOL_RESULT_PREVIEW_LENGTH == 500


class TestExtractRunId:
    """Tests for _extract_run_id helper function."""
    
    def test_extract_run_id_from_event_run(self):
        """Test extracting run_id from event.run.id."""
        event = {
            "run": {
                "id": "run_123"
            }
        }
        result = _extract_run_id(event)
        assert result == "run_123"
    
    def test_extract_run_id_with_node_name(self):
        """Test combining run_id with node_name."""
        event = {
            "run": {
                "id": "run_123"
            }
        }
        result = _extract_run_id(event, "test_node")
        assert result == "test_node_run_123"
    
    def test_extract_run_id_fallback_to_node_name(self):
        """Test fallback to node_name when run_id not available."""
        event = {}
        result = _extract_run_id(event, "test_node")
        assert result == "test_node"
    
    def test_extract_run_id_empty_when_no_fallback(self):
        """Test empty string when no run_id or node_name."""
        event = {}
        result = _extract_run_id(event)
        assert result == ""


class TestCreateEnvelopeEvent:
    """Tests for _create_envelope_event helper function."""
    
    def test_create_envelope_basic(self):
        """Test basic envelope creation."""
        result = _create_envelope_event(
            event_type="test_event",
            thread_id="thread_123",
            flow="chat",
            event_seq=1,
        )
        
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        
        # Parse the JSON
        json_str = result[6:-2]  # Remove "data: " and "\n\n"
        envelope = json.loads(json_str)
        
        assert envelope["type"] == "test_event"
        assert envelope["thread_id"] == "thread_123"
        assert envelope["flow"] == "chat"
        assert envelope["seq"] == 1
        assert "ts" in envelope
    
    def test_create_envelope_with_run_id(self):
        """Test envelope creation with run_id."""
        result = _create_envelope_event(
            event_type="test_event",
            thread_id="thread_123",
            flow="chat",
            event_seq=1,
            run_id="run_456",
        )
        
        json_str = result[6:-2]
        envelope = json.loads(json_str)
        
        assert envelope["run_id"] == "run_456"
    
    def test_create_envelope_with_payload(self):
        """Test envelope creation with payload."""
        payload = {"key": "value", "number": 42}
        result = _create_envelope_event(
            event_type="test_event",
            thread_id="thread_123",
            flow="chat",
            event_seq=1,
            payload=payload,
        )
        
        json_str = result[6:-2]
        envelope = json.loads(json_str)
        
        assert envelope["payload"] == payload


class TestShouldEmitThrottledSnapshot:
    """Tests for _should_emit_throttled_snapshot helper function."""
    
    def test_should_not_emit_too_soon(self):
        """Test that snapshot is not emitted if interval not passed."""
        current_time = 100.0
        last_snapshot_time = 95.0  # Only 5 seconds ago
        active_tasks = {}
        
        result = _should_emit_throttled_snapshot(
            current_time, last_snapshot_time, active_tasks
        )
        assert result is False
    
    def test_should_not_emit_no_long_running_tasks(self):
        """Test that snapshot is not emitted if no long-running tasks."""
        current_time = 100.0
        last_snapshot_time = 85.0  # 15 seconds ago (past interval)
        active_tasks = {
            "task1": {"started_at": 95.0}  # Only 5 seconds old
        }
        
        result = _should_emit_throttled_snapshot(
            current_time, last_snapshot_time, active_tasks
        )
        assert result is False
    
    def test_should_emit_with_long_running_task(self):
        """Test that snapshot is emitted when there's a long-running task."""
        current_time = 100.0
        last_snapshot_time = 85.0  # 15 seconds ago (past interval)
        active_tasks = {
            "task1": {"started_at": 75.0}  # 25 seconds old (past threshold)
        }
        
        result = _should_emit_throttled_snapshot(
            current_time, last_snapshot_time, active_tasks
        )
        assert result is True
    
    def test_should_emit_multiple_long_running_tasks(self):
        """Test that snapshot is emitted with multiple long-running tasks."""
        current_time = 100.0
        last_snapshot_time = 85.0
        active_tasks = {
            "task1": {"started_at": 75.0},  # 25 seconds old
            "task2": {"started_at": 70.0},  # 30 seconds old
        }
        
        result = _should_emit_throttled_snapshot(
            current_time, last_snapshot_time, active_tasks
        )
        assert result is True


class TestInitializeStreamState:
    """Tests for _initialize_stream_state helper function."""
    
    def test_initialize_stream_state_chat(self):
        """Test stream state initialization for chat flow."""
        initial_state = {"messages": []}
        config = {"configurable": {"thread_id": "test_thread"}}
        thread_id = "test_thread"
        flow = "chat"
        
        stream_state, flow_policy, event_seq, snapshot_seq = _initialize_stream_state(
            initial_state, config, thread_id, flow
        )
        
        assert isinstance(stream_state, StreamState)
        # event_seq is incremented during initialization (for graph_start event)
        assert stream_state.event_seq >= 0
        assert stream_state.snapshot_seq == 0
        assert stream_state.accumulated_content == ""
        assert stream_state.visited_nodes == []
        assert stream_state.current_node is None
        assert stream_state.active_tasks == {}
        assert stream_state.task_history == []
        assert stream_state.active_cluster_ids == set()
        assert stream_state.first_token_recorded is False
        
        assert isinstance(flow_policy, FlowPolicy)
        assert event_seq >= 0
        assert snapshot_seq >= 0
    
    def test_initialize_stream_state_report(self):
        """Test stream state initialization for report flow."""
        initial_state = {"raw_procedures": [{"id": "proc1"}]}
        config = {"configurable": {"thread_id": "test_thread"}}
        thread_id = "test_thread"
        flow = "report"
        
        stream_state, flow_policy, event_seq, snapshot_seq = _initialize_stream_state(
            initial_state, config, thread_id, flow
        )
        
        assert isinstance(stream_state, StreamState)
        assert isinstance(flow_policy, FlowPolicy)


class TestExtractChunkContent:
    """Tests for extract_chunk_content function (moved to llm.py)."""
    
    def test_extract_from_dict_content_string(self):
        """Test extracting content from dict with string content."""
        chunk = {"content": "Hello world"}
        result = extract_chunk_content(chunk)
        assert result == "Hello world"
    
    def test_extract_from_dict_content_list(self):
        """Test extracting content from dict with list content."""
        chunk = {"content": [{"text": "Hello"}, {"text": " world"}]}
        result = extract_chunk_content(chunk)
        assert result == "Hello world"
    
    def test_extract_from_dict_text_key(self):
        """Test extracting content from dict with text key."""
        chunk = {"text": "Hello world"}
        result = extract_chunk_content(chunk)
        assert result == "Hello world"
    
    def test_extract_from_dict_delta(self):
        """Test extracting content from dict with delta."""
        chunk = {"delta": {"content": "Hello"}}
        result = extract_chunk_content(chunk)
        assert result == "Hello"
    
    def test_skip_tool_call_chunks(self):
        """Test that tool call chunks without content are skipped."""
        chunk = {"tool_call_chunks": [{"name": "test"}]}
        result = extract_chunk_content(chunk)
        assert result is None
    
    def test_extract_from_object_content(self):
        """Test extracting content from object with content attribute."""
        class MockChunk:
            def __init__(self):
                self.content = "Hello world"
        
        chunk = MockChunk()
        result = extract_chunk_content(chunk)
        assert result == "Hello world"
    
    def test_extract_from_object_text(self):
        """Test extracting content from object with text attribute."""
        class MockChunk:
            def __init__(self):
                self.text = "Hello world"
        
        chunk = MockChunk()
        result = extract_chunk_content(chunk)
        assert result == "Hello world"
    
    def test_extract_none_for_empty(self):
        """Test that empty content returns None."""
        chunk = {"content": ""}
        result = extract_chunk_content(chunk)
        assert result is None
    
    def test_fallback_to_string(self):
        """Test fallback to string conversion."""
        chunk = 12345
        result = extract_chunk_content(chunk)
        assert result == "12345"


class TestProcessChatModelStreamEvent:
    """Tests for process_chat_model_stream_event function (moved to llm.py)."""
    
    def test_process_valid_chunk(self):
        """Test processing a valid chunk event."""
        event = {
            "data": {
                "chunk": {"content": "Hello"}
            }
        }
        accumulated = "Prev: "
        
        result = process_chat_model_stream_event(event, "thread_123", accumulated)
        
        assert result is not None
        incremental, new_accumulated = result
        assert incremental == "Hello"
        assert new_accumulated == "Prev: Hello"
    
    def test_process_invalid_event(self):
        """Test processing an invalid event."""
        event = {"data": "not a dict"}
        result = process_chat_model_stream_event(event, "thread_123", "")
        assert result is None
    
    def test_process_missing_chunk(self):
        """Test processing event without chunk."""
        event = {"data": {}}
        result = process_chat_model_stream_event(event, "thread_123", "")
        assert result is None
    
    def test_process_empty_chunk(self):
        """Test processing event with empty chunk."""
        event = {
            "data": {
                "chunk": {"content": ""}
            }
        }
        result = process_chat_model_stream_event(event, "thread_123", "")
        assert result is None


class TestProcessToolEventAsync:
    """Tests for _process_tool_event_async function."""
    
    @patch("app.api.streaming.async_events.get_tool_to_node_map")
    @patch("app.api.streaming.async_events.extract_tool_event_data")
    def test_process_tool_start(self, mock_extract, mock_get_map):
        """Test processing tool start event."""
        mock_extract.return_value = {
            "tool_name": "test_tool",
            "args_preview": "arg1, arg2",
            "result_preview": "",
        }
        mock_get_map.return_value = {"test_tool": "tool_node"}
        
        event = {"event": "on_tool_start"}
        visited_nodes = []
        
        result = _process_tool_event_async(
            event, "on_tool_start", "thread_123", visited_nodes,
            "org", "project", "chat", "run_123"
        )
        
        assert len(result) == 2  # node_start + tool_start
        assert result[0]["type"] == "node_start"
        assert result[0]["node"] == "tool_node"
        assert result[1]["type"] == "tool_start"
        assert result[1]["tool_name"] == "test_tool"
        assert "tool_node" in visited_nodes
    
    @patch("app.api.streaming.async_events.get_tool_to_node_map")
    @patch("app.api.streaming.async_events.extract_tool_event_data")
    def test_process_tool_end(self, mock_extract, mock_get_map):
        """Test processing tool end event."""
        mock_extract.return_value = {
            "tool_name": "test_tool",
            "args_preview": "arg1, arg2",
            "result_preview": "result",
        }
        mock_get_map.return_value = {"test_tool": "tool_node"}
        
        event = {"event": "on_tool_end"}
        visited_nodes = []
        
        result = _process_tool_event_async(
            event, "on_tool_end", "thread_123", visited_nodes,
            "org", "project", "chat", "run_123"
        )
        
        assert len(result) == 3  # node_start + tool_end + node_end
        assert result[0]["type"] == "node_start"
        assert result[1]["type"] == "tool_end"
        assert result[2]["type"] == "node_end"
        assert result[1]["result_preview"] == "result"
    
    @patch("app.api.streaming.async_events.get_tool_to_node_map")
    @patch("app.api.streaming.async_events.extract_tool_event_data")
    def test_process_tool_no_data(self, mock_extract, mock_get_map):
        """Test processing tool event with no data."""
        mock_extract.return_value = None
        
        event = {"event": "on_tool_start"}
        visited_nodes = []
        
        result = _process_tool_event_async(
            event, "on_tool_start", "thread_123", visited_nodes,
            "org", "project", "chat", "run_123"
        )
        
        assert result == []


class TestProcessNodeEventAsync:
    """Tests for _process_node_event_async function."""
    
    def test_process_node_start(self):
        """Test processing node start event."""
        flow_policy = FlowPolicy(
            node_filter=lambda n: n != "__start__",
            extract_input_preview=lambda d: "preview",
            extract_output_preview=lambda d: "preview",
            extract_metadata=lambda d: {},
        )
        
        event = {
            "name": "test_node",
            "event": "on_chain_start",
            "data": {"input": {"key": "value"}},
        }
        
        result = _process_node_event_async(
            event, "on_chain_start", "thread_123", None, [],
            "chat", {}, [], set(), flow_policy, ""
        )
        
        assert isinstance(result, NodeEventResult)
        assert len(result.events) == 1
        assert result.events[0]["type"] == "node_start"
        assert result.events[0]["node"] == "test_node"
        assert "test_node" in result.visited_nodes
        assert result.current_node == "test_node"
        assert result.should_snapshot is False
    
    def test_process_node_end(self):
        """Test processing node end event."""
        flow_policy = FlowPolicy(
            node_filter=lambda n: True,
            extract_input_preview=lambda d: "preview",
            extract_output_preview=lambda d: "output preview",
            extract_metadata=lambda d: {},
        )
        
        event = {
            "name": "test_node",
            "event": "on_chain_end",
            "data": {"output": {"key": "value"}},
        }
        
        active_tasks = {
            "test_node": {
                "node_name": "test_node",
                "run_id": "test_node",
                "started_at": time.time(),
            }
        }
        
        result = _process_node_event_async(
            event, "on_chain_end", "thread_123", "test_node", ["test_node"],
            "chat", active_tasks, [], set(), flow_policy, "test_node"
        )
        
        assert isinstance(result, NodeEventResult)
        assert len(result.events) == 1
        assert result.events[0]["type"] == "node_end"
        assert result.events[0]["node"] == "test_node"
        assert result.should_snapshot is True
        assert result.current_node is None
        assert len(result.task_history) == 1
    
    def test_process_node_filtered(self):
        """Test that filtered nodes are skipped."""
        flow_policy = FlowPolicy(
            node_filter=lambda n: n != "filtered_node",
            extract_input_preview=lambda d: "preview",
            extract_output_preview=lambda d: "preview",
            extract_metadata=lambda d: {},
        )
        
        event = {
            "name": "filtered_node",
            "event": "on_chain_start",
        }
        
        result = _process_node_event_async(
            event, "on_chain_start", "thread_123", None, [],
            "chat", {}, [], set(), flow_policy, ""
        )
        
        assert len(result.events) == 0
        assert result.should_snapshot is False
    
    def test_process_node_empty_name(self):
        """Test that nodes with empty names are skipped."""
        flow_policy = FlowPolicy(
            node_filter=lambda n: True,
            extract_input_preview=lambda d: "preview",
            extract_output_preview=lambda d: "preview",
            extract_metadata=lambda d: {},
        )
        
        event = {
            "name": "",
            "event": "on_chain_start",
        }
        
        result = _process_node_event_async(
            event, "on_chain_start", "thread_123", None, [],
            "chat", {}, [], set(), flow_policy, ""
        )
        
        assert len(result.events) == 0


class TestNodeEventResult:
    """Tests for NodeEventResult dataclass."""
    
    def test_node_event_result_creation(self):
        """Test creating a NodeEventResult instance."""
        result = NodeEventResult(
            events=[{"type": "test"}],
            current_node="test_node",
            visited_nodes=["test_node"],
            active_tasks={},
            task_history=[],
            active_cluster_ids=set(),
            should_snapshot=False,
        )
        
        assert len(result.events) == 1
        assert result.current_node == "test_node"
        assert result.should_snapshot is False


class TestStreamState:
    """Tests for StreamState dataclass."""
    
    def test_stream_state_creation(self):
        """Test creating a StreamState instance."""
        state = StreamState(
            event_seq=0,
            snapshot_seq=0,
            last_snapshot_time=time.time(),
            accumulated_content="",
            last_ai_message_content="",
            visited_nodes=[],
            current_node=None,
            active_tasks={},
            task_history=[],
            active_cluster_ids=set(),
            first_token_recorded=False,
        )
        
        assert state.event_seq == 0
        assert state.snapshot_seq == 0
        assert state.accumulated_content == ""
        assert state.visited_nodes == []
        assert state.current_node is None
        assert state.active_tasks == {}
        assert state.task_history == []
        assert state.active_cluster_ids == set()
        assert state.first_token_recorded is False
