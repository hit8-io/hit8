# ==============================================================================
# VARIABLES
# ==============================================================================
variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "hit8-poc"
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "europe-west1"
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "europe-west1-b"
}

variable "project_number" {
  description = "GCP Project Number"
  type        = string
  default     = "617962194338"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
  default     = "hit8-api"
}

variable "secret_name" {
  description = "Secret Manager secret name"
  type        = string
  default     = "doppler-hit8-prd"
}

variable "artifact_registry_repository" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "backend"
}

variable "artifact_registry_location" {
  description = "Artifact Registry location"
  type        = string
  default     = "europe-west1"
}

variable "image_tag" {
  description = "Docker image tag to use (e.g., '0.5.0-a1b2c3d'). If null, uses VERSION file. CI/CD builds images with format '{VERSION}-{SHORT_SHA}'."
  type        = string
  default     = null
}
