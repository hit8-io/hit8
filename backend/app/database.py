"""
Supabase database client initialization.

Note: This module is currently unused. The application uses direct PostgreSQL
connections via PostgresSaver for LangGraph checkpointing instead of the Supabase client.
"""
import os
from supabase import create_client, Client

def get_supabase_client() -> Client:
    """
    Get Supabase client instance.
    
    Note: This function is not currently used. The application uses direct
    PostgreSQL connections via DATABASE_CONNECTION_STRING instead.
    """
    raise NotImplementedError(
        "Supabase client is not configured. The application uses direct "
        "PostgreSQL connections via PostgresSaver instead."
    )

