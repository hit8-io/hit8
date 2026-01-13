provider "google" {
  project = var.project_id
  region  = var.region
  # Zone is unused for regional resources, but good to have if you add VMs later
  zone    = var.zone 
}

# Read version from VERSION file at project root
locals {
  image_version = trimspace(file("${path.root}/../VERSION"))
}

# ==============================================================================
# 1. SECURITY & IDENTITY (New Dedicated Service Account)
# ==============================================================================

# Create a dedicated Service Account for the API
resource "google_service_account" "api_runner" {
  account_id   = "api-runner-sa"
  display_name = "Cloud Run API Service Account"
  description  = "Dedicated identity for the API service"
}

# Grant Secret Access ONLY to this SA
resource "google_secret_manager_secret_iam_member" "api_secret_access" {
  secret_id = google_secret_manager_secret.doppler_secrets.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_runner.email}"
  
  depends_on = [google_secret_manager_secret.doppler_secrets]
}

# ==============================================================================
# 2. NETWORKING (VPC & Static IP)
# ==============================================================================

resource "google_compute_address" "egress_ip" {
  name   = "production-static-egress-ip"
  region = var.region
}

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

# ==============================================================================
# 3. STORAGE (Regional & Secure)
# ==============================================================================

# Terraform State
resource "google_storage_bucket" "terraform_state" {
  name                        = "hit8-poc-prd-tfstate"
  location                    = var.region      # Single Region
  storage_class               = "STANDARD"      # Regional Class
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }
  
  lifecycle_rule {
    condition {
      num_newer_versions = 10
    }
    action {
      type = "Delete"
    }
  }
}

# Chat Documents (Dev)
resource "google_storage_bucket" "chat_documents_dev" {
  name                        = "hit8-poc-dev-chat"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 1
    }
    action {
      type = "Delete"
    }
  }
}

# Chat Documents (Prd)
resource "google_storage_bucket" "chat_documents_prd" {
  name                        = "hit8-poc-prd-chat"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 1
    }
    action {
      type = "Delete"
    }
  }
}

# SECURE IAM: Grant access ONLY to specific buckets (Not Project Wide)
resource "google_storage_bucket_iam_member" "api_chat_access_dev" {
  bucket = google_storage_bucket.chat_documents_dev.name
  role   = "roles/storage.objectAdmin" # Read/Write/Delete
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

resource "google_storage_bucket_iam_member" "api_chat_access_prd" {
  bucket = google_storage_bucket.chat_documents_prd.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

# Vertex AI service account needs access to chat buckets for GCS operations
resource "google_storage_bucket_iam_member" "vertex_chat_access_dev" {
  bucket = google_storage_bucket.chat_documents_dev.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:vertex@hit8-poc.iam.gserviceaccount.com"
}

resource "google_storage_bucket_iam_member" "vertex_chat_access_prd" {
  bucket = google_storage_bucket.chat_documents_prd.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:vertex@hit8-poc.iam.gserviceaccount.com"
}

# ==============================================================================
# 4. ARTIFACTS & SECRETS (Co-located)
# ==============================================================================

resource "google_artifact_registry_repository" "backend_api" {
  location      = var.region # Co-located with Cloud Run
  repository_id = var.artifact_registry_repository
  description   = "Docker repository for backend API"
  format        = "DOCKER"
}

resource "google_secret_manager_secret" "doppler_secrets" {
  secret_id = var.secret_name
  replication {
    auto {}
  }
}

# ==============================================================================
# 5. CLOUD RUN SERVICE (V2 Upgrade)
# ==============================================================================

resource "google_cloud_run_v2_service" "api" {
  name     = var.service_name
  location = var.region
  
  template {
    service_account = google_service_account.api_runner.email
    timeout         = "300s"
    
    containers {
      # Note the URL uses var.region to match the regional repository
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend_api.repository_id}/api:${local.image_version}"
      
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
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.doppler_secrets.secret_id
            version = "latest"
          }
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.name
        subnetwork = google_compute_subnetwork.subnet.name
      }
      egress = "ALL_TRAFFIC"
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
  
  depends_on = [
    google_compute_router_nat.nat,
    google_secret_manager_secret_iam_member.api_secret_access
  ]
}

# IAM: Public Access
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Custom Domain Mapping: api.hit8.io -> Cloud Run Service
resource "google_cloud_run_domain_mapping" "api" {
  name     = "api.hit8.io"
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.api.name
  }
}

# ==============================================================================
# 6. CLOUD RUN JOB (V2 Upgrade)
# ==============================================================================

resource "google_cloud_run_v2_job" "report_job" {
  name               = "hit8-report-job"
  location           = var.region
  deletion_protection = true  # Enabled for production safety

  template {
    template {
      service_account = google_service_account.api_runner.email
      
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend_api.repository_id}/api:${local.image_version}"
        
        command = ["python", "-m", "app.cli.run_report_job"]
        
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        env {
          name  = "ENVIRONMENT"
          value = "prd"
        }

        env {
          name = "DOPPLER_SECRETS_JSON"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.doppler_secrets.secret_id
              version = "latest"
            }
          }
        }
      }
      
      timeout     = "3600s"
      max_retries = 0
      
      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.name
          subnetwork = google_compute_subnetwork.subnet.name
        }
        egress = "ALL_TRAFFIC"
      }
    }
    
    parallelism = 1
    task_count  = 1
  }
  
  depends_on = [google_secret_manager_secret_iam_member.api_secret_access]
}

# IAM: Allow API SA to invoke the Job
resource "google_cloud_run_v2_job_iam_member" "api_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.report_job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api_runner.email}"
}
