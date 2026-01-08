provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# 0. GCS Bucket for Terraform State
resource "google_storage_bucket" "terraform_state" {
  name          = "hit8-poc-prd-tfstate"
  location      = var.region
  force_destroy = false  # Prevent accidental deletion
  
  versioning {
    enabled = true  # Required for state locking
  }
  
  lifecycle_rule {
    condition {
      num_newer_versions = 10  # Keep last 10 versions
    }
    action {
      type = "Delete"
    }
  }
  
  uniform_bucket_level_access = true
}

# GCS Bucket for Chat Documents (Dev)
resource "google_storage_bucket" "chat_documents_dev" {
  name          = "hit8-poc-dev-chat"
  location      = var.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 1  # 24 hours (1 day)
    }
    action {
      type = "Delete"
    }
  }
}

# GCS Bucket for Chat Documents (Prd)
resource "google_storage_bucket" "chat_documents_prd" {
  name          = "hit8-poc-prd-chat"
  location      = var.region
  force_destroy = false
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 1  # 24 hours (1 day)
    }
    action {
      type = "Delete"
    }
  }
}

# IAM: Grant service account read and write access to all GCS buckets in project
resource "google_project_iam_member" "storage_object_creator" {
  project = var.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:vertex@hit8-poc.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:vertex@hit8-poc.iam.gserviceaccount.com"
}

# 1. The Static IP (Crucial to import this first to save it)
resource "google_compute_address" "egress_ip" {
  name   = "production-static-egress-ip"
  region = var.region
}

# 2. VPC and Subnet
resource "google_compute_network" "vpc" {
  name                    = "production-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "production-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# 3. Cloud Router & NAT
resource "google_compute_router" "router" {
  name    = "production-router"             
  network = google_compute_network.vpc.id
  region  = var.region
}

resource "google_compute_router_nat" "nat" {
  name                               = "production-nat-gateway" 
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.egress_ip.self_link]
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_PRIMARY_IP_RANGES"
}

# 4. Artifact Registry Repository
resource "google_artifact_registry_repository" "backend_api" {
  location      = var.artifact_registry_location
  repository_id = var.artifact_registry_repository
  description   = "Docker repository for backend API"
  format        = "DOCKER"
}

# 5. Secret Manager Secret
resource "google_secret_manager_secret" "doppler_secrets" {
  secret_id = var.secret_name
  
  replication {
    auto {}
  }
}

# 6. Cloud Run Service
# Note: Using default compute service account that already exists
# The service account is: ${var.project_number}-compute@developer.gserviceaccount.com
resource "google_cloud_run_service" "api" {
  name     = var.service_name
  location = var.region

  template {
    spec {
      # Using default compute service account (already exists, not managed by Terraform)
      # service_account_name is omitted to use the default
      
      containers {
        # Image tag is managed by deployment pipeline, not Terraform
        # Using :latest as placeholder - actual image is updated via gcloud during deployments
        image = "${var.artifact_registry_location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend_api.repository_id}/api:latest"
        
        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }

        env {
          name  = "ENVIRONMENT"
          value = "prd"
        }

        env {
          name = "DOPPLER_SECRETS_JSON"
          value_from {
            secret_key_ref {
              name = google_secret_manager_secret.doppler_secrets.secret_id
              key  = "latest"
            }
          }
        }
      }

      container_concurrency = 160  # Match current deployment
      timeout_seconds      = 300
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale"              = "0"
        "autoscaling.knative.dev/maxScale"              = "3"
        "run.googleapis.com/vpc-access-egress"        = "all-traffic"
        "run.googleapis.com/startup-cpu-boost"        = "true"  # Keep for better cold start performance
        "run.googleapis.com/network-interfaces"         = jsonencode([{
          network    = google_compute_network.vpc.name
          subnetwork = google_compute_subnetwork.subnet.name
        }])
      }
      labels = {
        environment = "prd"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    google_compute_network.vpc,
    google_compute_subnetwork.subnet
  ]
}

# 7. IAM: Allow unauthenticated access
resource "google_cloud_run_service_iam_member" "public_access" {
  service  = google_cloud_run_service.api.name
  location = google_cloud_run_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
