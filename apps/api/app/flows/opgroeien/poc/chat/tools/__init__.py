"""
Tools package for the opgroeien agent.

This module imports all tools and provides a get_all_tools() function.
Individual tools are organized in separate files in this directory.
"""
from __future__ import annotations

from typing import Any

# Import active tools
from app.flows.opgroeien.poc.chat.tools.extract_entities import extract_entities
from app.flows.opgroeien.poc.chat.tools.fetch_website import fetch_website
from app.flows.opgroeien.poc.chat.tools.generate_docx import generate_docx
from app.flows.opgroeien.poc.chat.tools.generate_xlsx import generate_xlsx
from app.flows.opgroeien.poc.chat.tools.get_procedure import get_procedure
from app.flows.opgroeien.poc.chat.tools.get_regelgeving import get_regelgeving
from app.flows.opgroeien.poc.chat.tools.procedures_vector_search import procedures_vector_search
from app.flows.opgroeien.poc.chat.tools.query_knowledge_graph import query_knowledge_graph
from app.flows.opgroeien.poc.chat.tools.regelgeving_vector_search import regelgeving_vector_search


def get_all_tools() -> list[Any]:
    """
    Get all active tools for the agent.
    
    To enable additional tools from this directory, import them above and add to this list.
    """
    return [
        procedures_vector_search,
        regelgeving_vector_search,
        fetch_website,
        get_procedure,
        get_regelgeving,
        extract_entities,
        query_knowledge_graph,
        generate_docx,
        generate_xlsx,
    ]
