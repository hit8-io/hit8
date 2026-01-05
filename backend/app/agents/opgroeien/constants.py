"""
Constants for the opgroeien agent.
"""
from __future__ import annotations

# Vector store collection names
COLLECTION_PROCEDURES = "embeddings_proc"
COLLECTION_REGELGEVING = "embeddings_regel"

# Graph node names
NODE_AGENT = "agent"
NODE_TOOLS = "tools"  # Legacy - kept for backward compatibility

# Individual tool node names
NODE_PROCEDURES_VECTOR_SEARCH = "node_procedures_vector_search"
NODE_REGELGEVING_VECTOR_SEARCH = "node_regelgeving_vector_search"
NODE_FETCH_WEBPAGE = "node_fetch_webpage"
NODE_GENERATE_DOCX = "node_generate_docx"
NODE_GENERATE_XLSX = "node_generate_xlsx"
NODE_EXTRACT_ENTITIES = "node_extract_entities"
NODE_QUERY_KNOWLEDGE_GRAPH = "node_query_knowledge_graph"
NODE_GET_PROCEDURE = "node_get_procedure"
NODE_GET_REGELGEVING = "node_get_regelgeving"

