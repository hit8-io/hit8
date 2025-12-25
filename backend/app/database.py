"""
Supabase database client initialization.
"""
import os
from supabase import create_client, Client

from app.config import settings

def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not service_role_key:
        raise ValueError("SUPABASE_SERVICE_ROLE_KEY environment variable is required")
    return create_client(settings.supabase_url, service_role_key)

