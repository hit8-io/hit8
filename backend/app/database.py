"""
Supabase database client initialization.
"""
import os
from supabase import create_client, Client

from app.config import settings

def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    return create_client(settings.supabase_url, os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

