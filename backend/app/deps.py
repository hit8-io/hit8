"""
Authentication dependencies for Google Identity Platform (Firebase Auth) token verification.
"""
import json
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth

from app.config import settings

# Lazy initialization flag
_firebase_initialized = False
_firebase_init_error = None


def _initialize_firebase():
    """Lazy initialization of Firebase Admin SDK - only called when needed."""
    global _firebase_initialized, _firebase_init_error
    
    if _firebase_initialized:
        return
    
    if firebase_admin._apps:
        _firebase_initialized = True
        return
    
    # Get service account JSON from settings (with fallback support)
    service_account_json = settings.get_firebase_service_account()
    
    if not service_account_json:
        _firebase_init_error = ValueError(
            "Firebase service account must be set via VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM environment variable"
        )
        print(f"Error: {_firebase_init_error}")
        return
    
    try:
        service_account_info = json.loads(service_account_json)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            'projectId': settings.gcp_project,
        })
        print(f"Initialized Firebase Admin SDK with service account for project: {settings.gcp_project}")
        
        _firebase_initialized = True
        _firebase_init_error = None
    except Exception as e:
        _firebase_init_error = e
        print(f"Warning: Firebase Admin SDK initialization failed: {e}")
        print("Token verification will fail until Firebase is properly configured.")
        # Don't raise - allow the app to start, but token verification will fail

# HTTP Bearer token security scheme
security = HTTPBearer()


async def verify_google_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify Google Identity Platform (Firebase Auth) ID token and return user info.
    
    Args:
        credentials: HTTP Bearer token from Authorization header (Firebase Auth ID token)
        
    Returns:
        dict: User information from verified token
        
    Raises:
        HTTPException: If token is invalid or missing
    """
    token = credentials.credentials
    
    # Initialize Firebase if not already done (lazy initialization)
    _initialize_firebase()
    
    if _firebase_init_error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Firebase Admin SDK not initialized: {str(_firebase_init_error)}. "
                   "Please set VERTEX_HIT8_POC_IAM_GSERVICEACCOUNT_COM environment variable."
        )
    
    # Log token info for debugging (first 20 chars only for security)
    print(f"Verifying Firebase Auth ID token: {token[:20]}... (length: {len(token)})")
    
    try:
        # Verify the Firebase Auth ID token
        decoded_token = auth.verify_id_token(token)
        
        # Extract user information
        uid = decoded_token.get('uid')
        email = decoded_token.get('email', '')
        name = decoded_token.get('name', '')
        picture = decoded_token.get('picture', '')
        email_verified = decoded_token.get('email_verified', False)
        
        print(f"Verified Firebase Auth token for user: {email} (uid: {uid})")
        
        return {
            'sub': uid,
            'email': email,
            'name': name,
            'picture': picture,
            'email_verified': email_verified,
        }
            
    except ValueError as e:
        print(f"Token verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except Exception as e:
        print(f"Auth error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {str(e)}"
        )

