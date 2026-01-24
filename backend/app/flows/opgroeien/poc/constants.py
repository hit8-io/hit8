"""
Constants for the opgroeien POC flow.
"""
from __future__ import annotations

from app import constants

# Config
ORG = "opgroeien"
PROJECT = "poc"
SYSTEM_PROMPT = "system_prompt"

# Vector store collection names
COLLECTION_PROCEDURES = "embeddings_proc"
COLLECTION_REGELGEVING = "embeddings_regel"

# Vector search parameters
VECTOR_SEARCH_DEFAULT_K = 40  # Default number of results for vector search
VECTOR_SEARCH_DOC_K = 10  # Number of results when searching for specific documents

# Embedding model configuration
EMBEDDING_MODEL_NAME = "models/gemini-embedding-001"
EMBEDDING_TASK_TYPE = "retrieval_document"
EMBEDDING_OUTPUT_DIMENSIONALITY = 1536  # Match database embedding dimensions
EMBEDDING_PROVIDER = "vertexai"

# Entity extraction model configuration
ENTITY_EXTRACTION_TEMPERATURE = 0.0
ENTITY_EXTRACTION_THINKING_LEVEL = None

# Graph node names
NODE_AGENT = "agent"
NODE_TOOLS = "tools"  # Legacy - kept for backward compatibility

# Individual tool node names
NODE_PROCEDURES_VECTOR_SEARCH = "node_procedures_vector_search"
NODE_REGELGEVING_VECTOR_SEARCH = "node_regelgeving_vector_search"
NODE_FETCH_WEBPAGE = "node_fetch_website"
NODE_GENERATE_DOCX = "node_generate_docx"
NODE_GENERATE_XLSX = "node_generate_xlsx"
NODE_EXTRACT_ENTITIES = "node_extract_entities"
NODE_QUERY_KNOWLEDGE_GRAPH = "node_query_knowledge_graph"
NODE_GET_PROCEDURE = "node_get_procedure"
NODE_GET_REGELGEVING = "node_get_regelgeving"

# Report generation batching
MAX_PARALLEL_WORKERS = constants.CONSTANTS.get("REPORT_MAX_PARALLEL_WORKERS", 2)

