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
  description = "Root domain name"
  type        = string
  default     = "hit8.io"
}

# --- SECRETS (Uit Doppler) ---

variable "SCW_PRD_DB_PWD" {
  description = "Production RDB (Postgres) password. Set via TF_VAR_SCW_PRD_DB_PWD or Doppler. Must be 8-128 characters, contain at least one digit, one uppercase, one lowercase, and one special character."
  type        = string
  sensitive   = true
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
