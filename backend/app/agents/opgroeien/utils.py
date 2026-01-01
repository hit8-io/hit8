"""
Utility functions for the opgroeien agent - vector stores and embeddings.
"""
from __future__ import annotations

import json

import structlog
from langchain_community.vectorstores.pgvector import PGVector
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.agents.opgroeien.constants import COLLECTION_PROCEDURES, COLLECTION_REGELGEVING
from app.config import settings

logger = structlog.get_logger(__name__)

# Cache embedding model
_embedding_model: GoogleGenerativeAIEmbeddings | None = None


def _get_embedding_model() -> GoogleGenerativeAIEmbeddings:
    """Get or create cached embedding model."""
    global _embedding_model
    if _embedding_model is None:
        import json
        from google.oauth2 import service_account
        
        service_account_info = json.loads(settings.vertex_service_account_json)
        project_id = service_account_info["project_id"]
        
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        
        _embedding_model = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001",
            task_type="retrieval_document",
            model_kwargs={"provider": "vertexai"},
            project=project_id,
            location=settings.vertex_ai_location,
            credentials=creds,
        )
    return _embedding_model


# Cache vector stores
_procedures_store: PGVector | None = None
_regelgeving_store: PGVector | None = None


def _get_procedures_vector_store() -> PGVector:
    """Get or create cached procedures vector store."""
    global _procedures_store
    if _procedures_store is None:
        embedding_model = _get_embedding_model()
        _procedures_store = PGVector(
            connection_string=settings.database_connection_string,
            embedding_function=embedding_model,
            collection_name=COLLECTION_PROCEDURES,
            distance_strategy="COSINE",
        )
    return _procedures_store


def _get_regelgeving_vector_store() -> PGVector:
    """Get or create cached regelgeving vector store."""
    global _regelgeving_store
    if _regelgeving_store is None:
        embedding_model = _get_embedding_model()
        _regelgeving_store = PGVector(
            connection_string=settings.database_connection_string,
            embedding_function=embedding_model,
            collection_name=COLLECTION_REGELGEVING,
            distance_strategy="COSINE",
        )
    return _regelgeving_store

