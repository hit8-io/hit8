"""
Agents directory for different agent implementations.
"""
from __future__ import annotations

from app.api.graph_manager import register_graph

# Import graph creation functions
from app.agents.opgroeien.graph import create_agent_graph
from app.agents.simple.graph import create_graph

# Register available graph types
register_graph("opgroeien", create_agent_graph)
register_graph("simple", create_graph)

