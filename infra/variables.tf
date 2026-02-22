# ==============================================================================
# VARIABLES (consolidated from gcp-variables, cf-variables, scw-variables)
# ==============================================================================

# --- Backend provider (frontend API URL) ---
variable "backend_provider" {
  description = "Backend for hit8 frontend: gcp or scw (Scaleway). Prd and stg use the same provider."
  type        = string
  default     = "scw"

  validation {
    condition     = contains(["gcp", "scw"], var.backend_provider)
    error_message = "backend_provider must be \"gcp\" or \"scw\"."
  }
}

# --- GCP ---
variable "GCP_PROJECT_ID" {
  description = "GCP Project ID"
  type        = string
  sensitive   = true
}

variable "GCP_REGION" {
  description = "GCP Region"
  type        = string
  default     = "europe-west1"
}

variable "GCP_ZONE" {
  description = "GCP Zone"
  type        = string
  default     = "europe-west1-b"
}

variable "SERVICE_NAME" {
  description = "Cloud Run service name"
  type        = string
  default     = "hit8-api"
}

variable "SECRET_NAME" {
  description = "Secret Manager secret name (legacy; Doppler tokens use doppler-token-prd/stg)"
  type        = string
  default     = "doppler-token-prd"
}

variable "ARTIFACT_REGISTRY_REPOSITORY" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "backend"
}

variable "ARTIFACT_REGISTRY_LOCATION" {
  description = "Artifact Registry location"
  type        = string
  default     = "europe-west1"
}

variable "IMAGE_TAG" {
  description = "Docker image tag to use (e.g., '0.5.0-a1b2c3d'). If null, uses VERSION file. CI/CD builds images with format '{VERSION}-{SHORT_SHA}'."
  type        = string
  default     = null
}

# --- Cloudflare ---
variable "CLOUDFLARE_ACCOUNT_ID" {
  description = "Cloudflare Account ID"
  type        = string
  sensitive   = true
}

variable "CLOUDFLARE_ZONE_ID" {
  description = "Zone ID for hit8.io"
  type        = string
  sensitive   = true
}

variable "DOMAIN_NAME" {
  description = "Root domain name"
  type        = string
  default     = "hit8.io"
}

# --- Scaleway ---
variable "SCW_PROJECT_ID" {
  description = "Scaleway Project ID (UUID)."
  type        = string
  sensitive   = true
}

variable "SCW_SECRET_KEY" {
  description = "Scaleway API secret key. Used by containers to fetch DOPPLER_TOKEN from Secret Manager at startup (same key as Terraform uses). Set via TF_VAR_SCW_SECRET_KEY or Doppler."
  type        = string
  sensitive   = true
}

variable "SCW_REGION" {
  description = "Scaleway Region"
  type        = string
  default     = "fr-par"
}

variable "SCW_ZONE" {
  description = "Scaleway Zone default"
  type        = string
  default     = "fr-par-2"
}

variable "CONTAINER_IMAGE" {
  description = "Container image tag (e.g. latest, v1.0.0). Full image = registry/api:<tag>."
  type        = string
  default     = "latest"
}

variable "DOMAIN_ROOT" {
  description = "Root domain name (Scaleway; same as DOMAIN_NAME)"
  type        = string
  default     = "hit8.io"
}

variable "SCW_PRD_DB_PWD" {
  description = "Production RDB (Postgres) password. Set via TF_VAR_SCW_PRD_DB_PWD or Doppler. Must be 8-128 characters, contain at least one digit, one uppercase, one lowercase, and one special character."
  type        = string
  sensitive   = true
}

# Optional: extra CIDRs allowed to reach prd Redis 6379 (e.g. ["10.0.0.0/8"] or ["0.0.0.0/0"] for debug). Default [].
variable "scw_redis_extra_inbound_cidrs" {
  description = "Extra IPv4 CIDRs allowed to connect to prd Redis port 6379 (debug: try [\"0.0.0.0/0\"] to test connectivity, then remove)."
  type        = list(string)
  default     = []
}

variable "DOPPLER_PROJECT" {
  description = "Doppler project name (e.g. hit8). Used with DOPPLER_TOKEN for doppler run in containers."
  type        = string
  default     = "hit8"
}

variable "DOPPLER_SERVICE_TOKENS" {
  description = "Map with tokens: { prd = '...', stg = '...' }. Used by GCP (Cloud Run). For Scaleway, the Doppler token is stored in Secret Manager and fetched by the container via API."
  type        = map(string)
  sensitive   = true
}
