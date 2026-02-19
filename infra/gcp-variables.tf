# ==============================================================================
# VARIABLES
# ==============================================================================
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
