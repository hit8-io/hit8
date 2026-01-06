"""
Authentication dependencies for Google Identity Platform (Firebase Auth) token verification.
"""
import json
import threading
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# Lazy Firebase initialization - only initialize when needed
_firebase_initialized = False
_firebase_init_lock = threading.Lock()

def _ensure_firebase_initialized() -> None:
    """Initialize Firebase Admin SDK if not already initialized."""
    global _firebase_initialized
    if not _firebase_initialized:
        with _firebase_init_lock:
            if not _firebase_initialized:
                try:
                    service_account_info = json.loads(settings.vertex_service_account)
                    cred = credentials.Certificate(service_account_info)
                    firebase_admin.initialize_app(cred, {'projectId': settings.gcp_project})
                    _firebase_initialized = True
                    logger.info("firebase_admin_initialized", project_id=settings.gcp_project)
                except Exception as e:
                    logger.error(
                        "firebase_admin_init_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
                    raise

security = HTTPBearer()


async def verify_google_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Verify Google Identity Platform ID token and return user info."""
    # Ensure Firebase is initialized before use
    _ensure_firebase_initialized()
    
    decoded_token = auth.verify_id_token(credentials.credentials)
    
    if 'email' not in decoded_token:
        raise ValueError("Email is required in ID token but not present")
    if 'name' not in decoded_token:
        raise ValueError("Name is required in ID token but not present")
    if 'picture' not in decoded_token:
        raise ValueError("Picture is required in ID token but not present")
    
    return {
        'sub': decoded_token['uid'],
        'email': decoded_token['email'],
        'name': decoded_token['name'],
        'picture': decoded_token['picture'],
    }

