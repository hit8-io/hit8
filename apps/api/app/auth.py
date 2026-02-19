"""
Authentication dependencies for Google Identity Platform (Firebase Auth) token verification.
"""
import json
import threading
from urllib.parse import quote
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
                    service_account_info = json.loads(settings.VERTEX_SERVICE_ACCOUNT)
                    cred = credentials.Certificate(service_account_info)
                    firebase_admin.initialize_app(cred, {'projectId': settings.GCP_PROJECT})
                    _firebase_initialized = True
                    logger.info("firebase_admin_initialized", project_id=settings.GCP_PROJECT)
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
    
    # Get name and picture from token, or fetch from user record if missing
    name = decoded_token.get('name')
    picture = decoded_token.get('picture')
    
    # If name or picture are missing from token, fetch from user record
    if not name or not picture:
        try:
            user_record = auth.get_user(decoded_token['uid'])
            if not name:
                name = user_record.display_name
            if not picture:
                picture = user_record.photo_url
        except Exception as e:
            logger.warning(
                "failed_to_fetch_user_record",
                uid=decoded_token['uid'],
                error=str(e),
                error_type=type(e).__name__,
            )
    
    # Provide defaults if still missing
    if not name:
        email = decoded_token['email']
        name = email.split('@')[0] if email else 'User'
    if not picture:
        # Generate a default avatar URL
        picture = f"https://ui-avatars.com/api/?name={quote(name)}&background=random"
    
    return {
        'sub': decoded_token['uid'],
        'email': decoded_token['email'],
        'name': name,
        'picture': picture,
    }

