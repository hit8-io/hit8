"""
Supabase database client initialization.
"""
import os
from supabase import create_client, Client
from typing import Optional

# Global Supabase client instance
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """
    Get or create the Supabase client instance.
    
    Uses SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from environment variables
    (injected by Doppler).
    
    Returns:
        Client: Supabase client instance
    """
    global _supabase_client
    
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment"
            )
        
        _supabase_client = create_client(supabase_url, supabase_key)
    
    return _supabase_client

