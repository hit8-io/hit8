variable "SCW_PROJECT_ID" {
  description = "Scaleway Project ID (UUID)."
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

variable "DOPPLER_SERVICE_TOKENS" {
  description = "Map with tokens: { prd = '...', stg = '...' }"
  type        = map(string)
  sensitive   = true
}
