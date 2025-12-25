"""
Authentication dependencies for Google Identity Platform (Firebase Auth) token verification.
"""
import json
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth

from app.config import settings

# Initialize Firebase Admin SDK
service_account_info = json.loads(settings.vertex_service_account_json)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {'projectId': settings.gcp_project})

security = HTTPBearer()


async def verify_google_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Verify Google Identity Platform ID token and return user info."""
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

