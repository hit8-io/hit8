"""
LiteLLM Router configuration for centralized rate limiting and model routing.
"""
import json
import os
import tempfile
import structlog
from litellm import Router

from app.config import settings

logger = structlog.get_logger(__name__)

# Quota configuration (adjust based on GCP Quota Console)
QUOTA_PRO_TPM = 250_000      # Preview/Experimental Tier (Strict)
QUOTA_FLASH_TPM = 5_000_000  # High Throughput Tier
QUOTA_OLLAMA_TPM = 10_000_000  # Effectively unlimited for local

# Get GCP project from settings
GCP_PROJECT = settings.GCP_PROJECT
if not GCP_PROJECT:
    raise ValueError("GCP_PROJECT is required in settings")

# Get Vertex AI service account credentials and write to temp file for GOOGLE_APPLICATION_CREDENTIALS
# LiteLLM and Google SDK require credentials to be accessible as a file on disk.
# Other parts of the codebase (storage.py, db.py, auth.py) create credentials objects directly,
# but LiteLLM's Router needs GOOGLE_APPLICATION_CREDENTIALS environment variable pointing to a file.
VERTEX_SERVICE_ACCOUNT_JSON = settings.VERTEX_SERVICE_ACCOUNT
if not VERTEX_SERVICE_ACCOUNT_JSON:
    raise ValueError("VERTEX_SERVICE_ACCOUNT is required in settings")

# Parse and validate the JSON
try:
    vertex_creds_dict = json.loads(VERTEX_SERVICE_ACCOUNT_JSON)
except json.JSONDecodeError as e:
    raise ValueError(f"VERTEX_SERVICE_ACCOUNT must be valid JSON: {e}")

# Validate required fields
required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
missing_fields = [field for field in required_fields if field not in vertex_creds_dict]
if missing_fields:
    raise ValueError(
        f"VERTEX_SERVICE_ACCOUNT missing required fields: {', '.join(missing_fields)}"
    )

# Write credentials to a temporary file and set GOOGLE_APPLICATION_CREDENTIALS
# File persists for the lifetime of the process (delete=False) so LiteLLM can access it.
# Using tempfile ensures unique filename and proper cleanup by OS on process exit.
_credentials_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
try:
    json.dump(vertex_creds_dict, _credentials_file, indent=None)
    _credentials_file.flush()
    _credentials_file.close()
    
    # Set restrictive permissions (read/write for owner only)
    os.chmod(_credentials_file.name, 0o600)
    
    # Set environment variable for Google SDK and LiteLLM
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = _credentials_file.name
    
    logger.info(
        "vertex_credentials_configured",
        credentials_file=_credentials_file.name,
        project_id=vertex_creds_dict.get("project_id"),
        client_email=vertex_creds_dict.get("client_email", "")[:20] + "..." if vertex_creds_dict.get("client_email") else None,
    )
except Exception as e:
    # Clean up file if writing failed
    try:
        os.unlink(_credentials_file.name)
    except Exception:
        pass
    raise ValueError(f"Failed to write credentials file: {e}") from e

# Also keep as JSON string for vertex_credentials parameter (backup/fallback)
# Some LiteLLM versions may prefer this over GOOGLE_APPLICATION_CREDENTIALS
VERTEX_CREDENTIALS = json.dumps(vertex_creds_dict)

# Get Ollama base URL from settings
OLLAMA_BASE_URL = None
for provider_config in settings.LLM_PROVIDER:
    if provider_config.PROVIDER == "ollama":
        OLLAMA_BASE_URL = provider_config.OLLAMA_BASE_URL
        break

model_list = [
    # Gemini 2.5 Pro
    {
        "model_name": "gemini-2.5-pro",
        "litellm_params": {
            "model": "vertex_ai/gemini-2.5-pro",
            "vertex_project": GCP_PROJECT,
            "vertex_location": "global",
            "vertex_credentials": VERTEX_CREDENTIALS,
            "tpm": QUOTA_PRO_TPM,
            "rpm": 5,
            "timeout": 600,
        }
    },
    # Gemini 2.5 Flash
    {
        "model_name": "gemini-2.5-flash",
        "litellm_params": {
            "model": "vertex_ai/gemini-2.5-flash",
            "vertex_project": GCP_PROJECT,
            "vertex_location": "global",
            "vertex_credentials": VERTEX_CREDENTIALS,
            "tpm": QUOTA_FLASH_TPM,
            "rpm": 60,
        }
    },
    # Gemini 2.0 Flash Lite
    {
        "model_name": "gemini-2.0-flash-lite-001",
        "litellm_params": {
            "model": "vertex_ai/gemini-2.0-flash-lite-001",
            "vertex_project": GCP_PROJECT,
            "vertex_location": "global",
            "vertex_credentials": VERTEX_CREDENTIALS,
            "tpm": QUOTA_FLASH_TPM,
            "rpm": 60,
        }
    },
    # Gemini 3.0 Pro Preview
    {
        "model_name": "gemini-3-pro-preview",
        "litellm_params": {
            "model": "vertex_ai/gemini-3-pro-preview",
            "vertex_project": GCP_PROJECT,
            "vertex_location": "global",
            "vertex_credentials": VERTEX_CREDENTIALS,
            "tpm": QUOTA_PRO_TPM,
            "rpm": 5,
            "timeout": 1200,  # Extra long for thinking
        }
    },
    # Gemini 3.0 Flash Preview
    {
        "model_name": "gemini-3-flash-preview",
        "litellm_params": {
            "model": "vertex_ai/gemini-3-flash-preview",
            "vertex_project": GCP_PROJECT,
            "vertex_location": "global",
            "vertex_credentials": VERTEX_CREDENTIALS,
            "tpm": QUOTA_FLASH_TPM,
            "rpm": 10,
        }
    },
]

# Add Ollama model if configured
if OLLAMA_BASE_URL:
    model_list.append({
        "model_name": "llama3.1:8b",
        "litellm_params": {
            "model": "ollama/llama3.1:8b",
            "api_base": OLLAMA_BASE_URL,
            "tpm": QUOTA_OLLAMA_TPM,
        }
    })

# Initialize router (in-memory mode, no Redis)
router = Router(
    model_list=model_list,
    num_retries=3,      # Retry 5xx and 429 errors automatically
    allowed_fails=1,    # Allow 1 fail before cooldown
    cooldown_time=120,  # Wait 120s if model fails (e.g. 429) - longer for rate limits
    set_verbose=True     # Enable logs to see rate limiting
)

logger.info(
    "litellm_router_initialized",
    model_count=len(model_list),
    gcp_project=GCP_PROJECT,
    ollama_configured=OLLAMA_BASE_URL is not None,
)
