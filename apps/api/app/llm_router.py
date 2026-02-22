"""
LiteLLM Router configuration for centralized rate limiting and model routing.

Setup (this module):
- Router is created with model_list (Vertex + optional Ollama), routing_strategy="simple-shuffle",
  and when CACHE_ENABLED + REDIS_HOST: redis_host/port/password, cache_responses=True,
  cache_kwargs (ssl, socket_connect_timeout, socket_timeout). Router handles retries and cooldown.

Usage:
- All LLM calls go through this Router via flows/common.py: get_llm() -> _create_model() -> ChatLiteLLM(router=router, model=...).
- Caching: Router caches completion responses in Redis (async set after each completion). Cache reads
  happen inside LiteLLM before calling the provider. TTL comes from LiteLLM defaults / config.
- Rate limiting: Router uses Redis for distributed rate limiting (TPM/RPM per model).
"""
import json
import os
import tempfile
import structlog
from litellm import Router

from app.config import settings
from app.constants import CONSTANTS

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

# 1. CONFIGURATION: Get Location & Fallback Preference
VERTEX_LOCATION = None
USE_ALTERNATIVE = False

for llm_config in CONSTANTS["LLM"]:
    if llm_config.get("PROVIDER") == "vertex":
        VERTEX_LOCATION = llm_config.get("LOCATION")
        # Check if alternative endpoint (global) is enabled in config
        USE_ALTERNATIVE = llm_config.get("USE_ALTERNATIVE", False)
        break

# Define target locations: Preferred first, then Global if enabled
deployment_locations = [VERTEX_LOCATION]
if USE_ALTERNATIVE:
    deployment_locations.append("global")

# Remove duplicates (e.g., if VERTEX_LOCATION is already 'global')
deployment_locations = list(dict.fromkeys(filter(None, deployment_locations)))


# 2. HELPER: Generate configs for all active locations
def _create_vertex_configs(model_name: str, vertex_path: str, tpm: int, rpm: int, timeout: int | None = None) -> list[dict]:
    """Generates a list of model configs for all active deployment locations."""
    configs = []
    for location in deployment_locations:
        params = {
            "model": vertex_path,
            "vertex_project": GCP_PROJECT,
            "vertex_location": location,
            "vertex_credentials": VERTEX_CREDENTIALS,
            "tpm": tpm,
            "rpm": rpm,
        }
        if timeout:
            params["timeout"] = timeout
            
        configs.append({
            "model_name": model_name,
            "litellm_params": params
        })
    return configs


# 3. MODEL DEFINITIONS: Dynamic generation
model_list = []

# Gemini 2.5 Pro
model_list.extend(_create_vertex_configs(
    model_name="gemini-2.5-pro",
    vertex_path="vertex_ai/gemini-2.5-pro",
    tpm=QUOTA_PRO_TPM,
    rpm=5,
    timeout=600
))

# Gemini 2.5 Flash
model_list.extend(_create_vertex_configs(
    model_name="gemini-2.5-flash",
    vertex_path="vertex_ai/gemini-2.5-flash",
    tpm=QUOTA_FLASH_TPM,
    rpm=60
))

# Gemini 2.0 Flash Lite
model_list.extend(_create_vertex_configs(
    model_name="gemini-2.0-flash-lite-001",
    vertex_path="vertex_ai/gemini-2.0-flash-lite-001",
    tpm=QUOTA_FLASH_TPM,
    rpm=60
))

# Gemini 3.0 Pro Preview
model_list.extend(_create_vertex_configs(
    model_name="gemini-3-pro-preview",
    vertex_path="vertex_ai/gemini-3-pro-preview",
    tpm=QUOTA_PRO_TPM,
    rpm=5,
    timeout=1200
))

# Gemini 3.0 Flash Preview
model_list.extend(_create_vertex_configs(
    model_name="gemini-3-flash-preview",
    vertex_path="vertex_ai/gemini-3-flash-preview",
    tpm=QUOTA_FLASH_TPM,
    rpm=10
))

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


# 4. ROUTER INITIALIZATION: Load Balancing
# simple-shuffle: Even distribution, no latency-tracking (avoids LiteLLM bug where
# async_log_success_event gets kwargs["litellm_params"] is None -> 'NoneType' has no attribute 'get').
router_kwargs = {
    "model_list": model_list,
    "routing_strategy": "simple-shuffle",
    "num_retries": 2,       # Retry on 5xx/429
    "allowed_fails": 1,     # Allow 1 failure before cooldown
    "cooldown_time": 30,    # Short cooldown to quickly retry failed region
    "set_verbose": settings.LOG_LEVEL.upper() == "DEBUG",  # Verbose when log level is DEBUG
}

# Add Redis for distributed rate limiting and caching (stg/prd)
# Password: Upstash requires one; private Redis (e.g. Scaleway) often passwordless.
# TLS: Use TLS for Upstash (by hostname) or when not Scaleway; no TLS for Scaleway private Redis.
_redis_host_lower = (settings.REDIS_HOST or "").strip().lower()
_redis_use_tls = "upstash" in _redis_host_lower or os.getenv("BACKEND_PROVIDER", "").strip().lower() != "scw"
# Redis cache: response caching + rate limiting. Use generous timeouts so async set() completes
# (LiteLLM creates the Redis client lazily on first cache write; first connection can be slow).
# Disable response cache on Scaleway: LiteLLM's Redis client times out on connect/set in VPC
# despite cache_kwargs and REDIS_SOCKET_* env; rate limiting still uses Redis.
_backend_provider = os.getenv("BACKEND_PROVIDER", "").strip().lower()
_cache_responses = _backend_provider != "scw"
if settings.CACHE_ENABLED and settings.REDIS_HOST:
    router_kwargs.update({
        "redis_host": settings.REDIS_HOST,
        "redis_port": 6379,
        "redis_password": settings.REDIS_PWD or None,
        "cache_responses": _cache_responses,
        "cache_kwargs": {
            "ssl": _redis_use_tls,  # True for Upstash (GCP), False for Scaleway internal Redis
            "socket_connect_timeout": 30,  # First connection / pool init can be slow (e.g. Scaleway VPC)
            "socket_timeout": 30,
            # Note: TTL is handled by LiteLLM's caching layer
        },
    })
    
    _features = ["distributed_rate_limiting", "cooldown_sync"]
    if _cache_responses:
        _features.insert(0, "response_caching")
    logger.info(
        "litellm_router_redis_enabled",
        redis_host=settings.REDIS_HOST,
        cache_ttl=settings.CACHE_TTL,
        cache_responses=_cache_responses,
        features=_features,
    )

router = Router(**router_kwargs)

logger.info(
    "litellm_router_initialized",
    model_count=len(model_list),
    gcp_project=GCP_PROJECT,
    ollama_configured=OLLAMA_BASE_URL is not None,
    vertex_location=VERTEX_LOCATION,
    deployment_locations=deployment_locations,
    use_alternative=USE_ALTERNATIVE,
    routing_strategy="simple-shuffle",
    redis_enabled=settings.CACHE_ENABLED and settings.REDIS_HOST is not None,
)
