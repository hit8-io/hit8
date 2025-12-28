"""
SIMPLIFIED FastAPI application entrypoint for debugging startup issues.

This is a minimal version to test if the app can start in Cloud Run.
"""
from __future__ import annotations

import sys
import os

# STARTUP_MARKER_1: Basic imports
print("STARTUP_MARKER_1: Starting Python application", file=sys.stderr, flush=True)

# STARTUP_MARKER_2: Parse Doppler secrets
print("STARTUP_MARKER_2: Parsing Doppler secrets", file=sys.stderr, flush=True)
doppler_secrets_json = os.getenv("DOPPLER_SECRETS_JSON")
if doppler_secrets_json:
    import json
    try:
        secrets = json.loads(doppler_secrets_json)
        for key, value in secrets.items():
            if key not in os.environ:
                os.environ[key] = str(value)
        print(f"STARTUP_MARKER_2: Loaded {len(secrets)} secrets", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"STARTUP_MARKER_2_ERROR: Failed to parse secrets: {e}", file=sys.stderr, flush=True)
        # Continue anyway - might work without secrets
else:
    print("STARTUP_MARKER_2: No DOPPLER_SECRETS_JSON found", file=sys.stderr, flush=True)

# STARTUP_MARKER_3: Import FastAPI
print("STARTUP_MARKER_3: Importing FastAPI", file=sys.stderr, flush=True)
try:
    from fastapi import FastAPI
    print("STARTUP_MARKER_3: FastAPI imported successfully", file=sys.stderr, flush=True)
except Exception as e:
    print(f"STARTUP_MARKER_3_ERROR: Failed to import FastAPI: {e}", file=sys.stderr, flush=True)
    raise

# STARTUP_MARKER_4: Create FastAPI app
print("STARTUP_MARKER_4: Creating FastAPI app", file=sys.stderr, flush=True)
try:
    app = FastAPI(title="Hit8 API", version="1.0.0")
    print("STARTUP_MARKER_4: FastAPI app created", file=sys.stderr, flush=True)
except Exception as e:
    print(f"STARTUP_MARKER_4_ERROR: Failed to create app: {e}", file=sys.stderr, flush=True)
    raise

# STARTUP_MARKER_5: Add health endpoint (no dependencies)
print("STARTUP_MARKER_5: Adding health endpoint", file=sys.stderr, flush=True)
@app.get("/health")
async def health():
    """Minimal health check - no dependencies."""
    return {"status": "ok", "message": "App is running"}

print("STARTUP_MARKER_5: Health endpoint added", file=sys.stderr, flush=True)

# STARTUP_MARKER_6: Try to import settings (non-blocking)
print("STARTUP_MARKER_6: Attempting to import settings", file=sys.stderr, flush=True)
try:
    from app.config import settings
    print("STARTUP_MARKER_6: Settings imported successfully", file=sys.stderr, flush=True)
    print(f"STARTUP_MARKER_6: App name: {settings.app_name}", file=sys.stderr, flush=True)
except Exception as e:
    print(f"STARTUP_MARKER_6_ERROR: Failed to import settings: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)
    # Continue - app can still run with minimal functionality

# STARTUP_MARKER_7: Startup complete
print("STARTUP_MARKER_7: Application startup complete - ready to accept requests", file=sys.stderr, flush=True)

