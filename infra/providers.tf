# This merges with your backend.tf configuration
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 7.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
  user_project_override = true
}

provider "cloudflare" {
  # API token is provided via CLOUDFLARE_API_TOKEN environment variable (set via Doppler)
  # Minimal retries to fail fast on authentication/IP restriction errors
  retries            = 1
  min_backoff        = 1
  max_backoff        = 2
  # Enable API client logging for better error messages
  api_client_logging = true
}
