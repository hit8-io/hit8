# ==============================================================================
# LOCALS
# ==============================================================================
locals {
  # Assumes VERSION file is in the root (where you run terraform) or parent
  # Adjust path as needed: "${path.module}/../VERSION"
  image_version = trimspace(file("${path.module}/../VERSION"))

  envs = {
    prd = {
      suffix    = "-prd"
      host      = "api-prd"
      secret_id = "doppler-hit8-prd"
    }
    stg = {
      suffix    = "-stg"
      host      = "api-stg"
      secret_id = "doppler-hit8-stg"
    }
  }
}

# ==============================================================================
# NETWORK
# ==============================================================================
# Network resources use "production-" prefix for historical reasons (except egress_ip which was renamed)
# They are shared across all environments (prd, stg, dev) despite the name
resource "google_compute_address" "egress_ip" {
  name   = "shared-static-egress-ip"  # Already renamed in GCP
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
# STORAGE
# ==============================================================================
# Artifact Registry
resource "google_artifact_registry_repository" "backend_api" {
  location      = var.region
  repository_id = var.artifact_registry_repository # Uses "backend"
  description   = "Docker repository for backend API"
  format        = "DOCKER"
}

# Chat Documents (Dev)
resource "google_storage_bucket" "chat_documents_dev" {
  name                        = "${var.project_id}-dev-chat"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition { age = 1 }
    action { type = "Delete" }
  }
}

# Chat Documents (Prd)
resource "google_storage_bucket" "chat_documents_prd" {
  name                        = "${var.project_id}-prd-chat"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition { age = 1 }
    action { type = "Delete" }
  }
}

# Chat Documents (Stg)
resource "google_storage_bucket" "chat_documents_stg" {
  name                        = "${var.project_id}-stg-chat"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition { age = 1 }
    action { type = "Delete" }
  }
}

# Function Source Code
resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-functions"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition { age = 30 }
    action { type = "Delete" }
  }
}

# Terraform State Bucket
# This bucket is cross-environment and stores Terraform state for all environments (prd, stg, dev)
# The name includes "prd" for historical reasons, but it's shared across all environments
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

# ==============================================================================
# SECURITY
# ==============================================================================
# Vertex AI Service Account (Existing)
# You must import this: 
# terraform import google_service_account.vertex_sa projects/hit8-poc/serviceAccounts/vertex@hit8-poc.iam.gserviceaccount.com
resource "google_service_account" "vertex_sa" {
  account_id   = "vertex" # Matches the part before @hit8-poc...
  display_name = "Vertex AI Service Account"
}

# Grant "Vertex AI User" role (Project Level)
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.vertex_sa.email}"
}

# API Runner Service Account
resource "google_service_account" "api_runner" {
  account_id   = "api-runner-sa"
  display_name = "Cloud Run API Service Account"
  description  = "Dedicated identity for the API service"
}

# Secrets
# Ensure var.secret_name == "doppler-hit8-prd"
resource "google_secret_manager_secret" "doppler_secrets" {
  secret_id = var.secret_name 
  replication {
    auto {} 
  }
}

resource "google_secret_manager_secret" "doppler_stg" {
  secret_id   = "doppler-hit8-stg"
  replication {
    auto {}
  }
}

# Grant Secret Access (Corrected to refer to the specific resources created above)
resource "google_secret_manager_secret_iam_member" "api_secret_access" {
  for_each = local.envs

  # Logic: If key is prd, use the resource "doppler_secrets". If stg, use "doppler_stg"
  # This prevents "unknown resource" errors if you try to reference by string ID alone
  secret_id = each.key == "prd" ? google_secret_manager_secret.doppler_secrets.id : google_secret_manager_secret.doppler_stg.id
  
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_runner.email}"
}

# ==============================================================================
# COMPUTE
# ==============================================================================
# Cloud Run Service
resource "google_cloud_run_v2_service" "api" {
  for_each = local.envs

  name     = "hit8-api${each.value.suffix}"  # hit8-api-prd / hit8-api-stg
  location = var.region

  template {
    service_account = google_service_account.api_runner.email
    timeout         = "300s"

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository}/api:${local.image_version}"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }

      env {
        name  = "ENVIRONMENT"
        value = each.key # prd / stg
      }

      env {
        name = "DOPPLER_SECRETS_JSON"
        value_source {
          secret_key_ref {
            secret  = each.value.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        timeout_seconds       = 240
        period_seconds        = 240
        failure_threshold     = 1
        tcp_socket {
          port = 8080
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    # Share the existing network
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

# Allow Public Access
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  for_each = google_cloud_run_v2_service.api

  project  = var.project_id
  location = each.value.location
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Domain Mapping
resource "google_cloud_run_domain_mapping" "api" {
  for_each = local.envs

  name     = "${each.value.host}.hit8.io" # api-prd.hit8.io / api-stg.hit8.io
  location = var.region
  metadata { namespace = var.project_id }

  spec {
    route_name = google_cloud_run_v2_service.api[each.key].name
  }

  depends_on = [google_cloud_run_v2_service.api]
}

# ==============================================================================
# CLOUD RUN JOB (Now Deploying Prd & Stg)
# ==============================================================================
resource "google_cloud_run_v2_job" "report_job" {
  for_each = local.envs  # <--- LOOP ENABLED

  name                = "hit8-report-job${each.value.suffix}" # hit8-report-job-prd / -stg
  location            = var.region
  deletion_protection = true

  template {
    template {
      service_account = google_service_account.api_runner.email
      
      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository}/api:${local.image_version}"
        
        command = ["python", "-m", "app.cli.run_report_job"]
        
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }

        # DYNAMIC ENVIRONMENT
        env {
          name  = "ENVIRONMENT"
          value = each.key # "prd" or "stg"
        }

        # DYNAMIC SECRET
        env {
          name = "DOPPLER_SECRETS_JSON"
          value_source {
            secret_key_ref {
              secret  = each.value.secret_id # doppler-hit8-prd / -stg
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
  
  # Depend on the IAM permissions for the secrets
  depends_on = [google_secret_manager_secret_iam_member.api_secret_access]
}

# ==============================================================================
# JOB IAM (Allow API SA to invoke BOTH jobs)
# ==============================================================================
resource "google_cloud_run_v2_job_iam_member" "api_invoker" {
  for_each = google_cloud_run_v2_job.report_job # <--- LOOP OVER JOBS

  project  = var.project_id
  location = var.region
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api_runner.email}"
}

# ==============================================================================
# FUNCTIONS
# ==============================================================================
# Enable Identity Platform API
resource "google_project_service" "identity_platform" {
  provider = google-beta
  project  = var.project_id
  service  = "identitytoolkit.googleapis.com"
  
  disable_on_destroy = false
}

# Package source
data "archive_file" "on_before_user_created_source" {
  type        = "zip"
  source_dir  = "${path.module}/functions/onBeforeUserCreated-v2"
  output_path = "${path.module}/functions/onBeforeUserCreated-v2.zip"
}

# Upload source
resource "google_storage_bucket_object" "on_before_user_created_source" {
  name   = "onBeforeUserCreated-v2-${data.archive_file.on_before_user_created_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.on_before_user_created_source.output_path
}

# Lookup Identity Platform Service Agent
resource "google_project_service_identity" "identity_platform_agent" {
  provider = google-beta
  service  = "identitytoolkit.googleapis.com"
  project  = var.project_id
  
  depends_on = [google_project_service.identity_platform]
}

# Deploy Gen 1 Function
resource "google_cloudfunctions_function" "on_before_user_created" {
  name        = "onBeforeUserCreated-v2"
  description = "Firebase Auth blocking hook"
  runtime     = "nodejs20"
  region      = var.region
  
  available_memory_mb = 256
  entry_point         = "onBeforeUserCreated"
  trigger_http        = true
  
  source_archive_bucket = google_storage_bucket.function_source.name
  source_archive_object = google_storage_bucket_object.on_before_user_created_source.name
  
  # Allow all at network level, restrict via IAM below
  ingress_settings = "ALLOW_ALL"
  
  depends_on = [
    google_storage_bucket_object.on_before_user_created_source
  ]
}

# SECURE IAM: Allow ONLY Identity Platform to invoke
resource "google_cloudfunctions_function_iam_member" "identity_platform_invoker" {
  project        = var.project_id
  region         = var.region
  cloud_function = google_cloudfunctions_function.on_before_user_created.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_project_service_identity.identity_platform_agent.email}"
}

# Configure Identity Platform to use the blocking function
resource "google_identity_platform_config" "auth_config" {
  provider = google-beta
  project  = var.project_id

  blocking_functions {
    triggers {
      event_type   = "beforeCreate"
      function_uri = google_cloudfunctions_function.on_before_user_created.https_trigger_url
    }
  }
  
  depends_on = [
    google_project_service.identity_platform,
    google_cloudfunctions_function.on_before_user_created
  ]
}

# ==============================================================================
# BUCKET IAM
# ==============================================================================
# API Runner Access (Dev)
resource "google_storage_bucket_iam_member" "api_chat_access_dev" {
  bucket = google_storage_bucket.chat_documents_dev.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

# API Runner Access (Prd)
resource "google_storage_bucket_iam_member" "api_chat_access_prd" {
  bucket = google_storage_bucket.chat_documents_prd.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

# API Runner Access (Stg)
resource "google_storage_bucket_iam_member" "api_chat_access_stg" {
  bucket = google_storage_bucket.chat_documents_stg.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

# Vertex SA Access (Dev)
resource "google_storage_bucket_iam_member" "vertex_chat_access_dev" {
  bucket = google_storage_bucket.chat_documents_dev.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vertex_sa.email}"
}

# Vertex SA Access (Prd)
resource "google_storage_bucket_iam_member" "vertex_chat_access_prd" {
  bucket = google_storage_bucket.chat_documents_prd.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vertex_sa.email}"
}

# Vertex SA Access (Stg)
resource "google_storage_bucket_iam_member" "vertex_chat_access_stg" {
  bucket = google_storage_bucket.chat_documents_stg.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vertex_sa.email}"
}
