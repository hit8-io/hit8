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
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.39"
    }
  }
}

provider "google" {
  project = var.GCP_PROJECT_ID
  region  = var.GCP_REGION
  zone    = var.GCP_ZONE
}

provider "google-beta" {
  project               = var.GCP_PROJECT_ID
  region                = var.GCP_REGION
  zone                  = var.GCP_ZONE
  user_project_override = true
}

provider "cloudflare" {
  # API token is provided via CLOUDFLARE_API_TOKEN environment variable (set via Doppler)
}

provider "scaleway" {
  region     = var.SCW_REGION
  zone       = var.SCW_ZONE
  project_id = var.SCW_PROJECT_ID
  # Access Key / Secret Key picked up from ENV vars (SCW_ACCESS_KEY, SCW_SECRET_KEY)
}
