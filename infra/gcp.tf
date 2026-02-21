# ==============================================================================
# LOCALS
# ==============================================================================
locals {
  # Assumes VERSION file is in the root (where you run terraform) or parent
  # Adjust path as needed: "${path.module}/../VERSION"
  # Note: Image tags are managed by CI/CD, not Terraform. This is only used for initial resource creation.
  # CI/CD builds images with tags: {VERSION}-{SHORT_SHA} and updates Cloud Run services/jobs after each build.
  image_version = var.IMAGE_TAG != null ? var.IMAGE_TAG : trimspace(file("${path.module}/../VERSION"))

  envs = {
    prd = {
      suffix          = "-prd"
      host            = "api-prd"
      token_secret_id = "doppler-token-prd"
    }
    stg = {
      suffix          = "-stg"
      host            = "api-stg"
      token_secret_id = "doppler-token-stg"
    }
  }
}

# ==============================================================================
# NETWORK
# ==============================================================================
# Network resources use "production-" prefix for historical reasons (except egress_ip which was renamed)
# They are shared across all environments (prd, stg, dev) despite the name
resource "google_compute_address" "egress_ip" {
  name   = "shared-static-egress-ip" # Already renamed in GCP
  region = var.GCP_REGION
}

resource "google_compute_network" "vpc" {
  name                    = "production-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "production-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.GCP_REGION
  network       = google_compute_network.vpc.id
}

resource "google_compute_router" "router" {
  name    = "production-router"
  network = google_compute_network.vpc.id
  region  = var.GCP_REGION
}

resource "google_compute_router_nat" "nat" {
  name                               = "production-nat-gateway"
  router                             = google_compute_router.router.name
  region                             = var.GCP_REGION
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.egress_ip.self_link]
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_PRIMARY_IP_RANGES"
}

# ==============================================================================
# STORAGE
# ==============================================================================
# Artifact Registry
resource "google_artifact_registry_repository" "backend_api" {
  location      = var.GCP_REGION
  repository_id = var.ARTIFACT_REGISTRY_REPOSITORY
  description   = "Docker repository for backend API"
  format        = "DOCKER"

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-most-recent-5"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }

  cleanup_policies {
    id     = "delete-older-versions"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "86400s"
    }
  }
}

# Chat Documents (Dev)
resource "google_storage_bucket" "chat_documents_dev" {
  name                        = "${var.GCP_PROJECT_ID}-dev-chat"
  location                    = var.GCP_REGION
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    environment = "dev"
    project     = "hit8"
    managed_by  = "terraform"
    purpose     = "chat-documents"
  }

  autoclass {
    enabled = true
  }
  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }
}

# Chat Documents (Prd)
resource "google_storage_bucket" "chat_documents_prd" {
  name                        = "${var.GCP_PROJECT_ID}-prd-chat"
  location                    = var.GCP_REGION
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    environment = "prd"
    project     = "hit8"
    managed_by  = "terraform"
    purpose     = "chat-documents"
  }

  autoclass {
    enabled = true
  }
  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }
}

# Chat Documents (Stg)
resource "google_storage_bucket" "chat_documents_stg" {
  name                        = "${var.GCP_PROJECT_ID}-stg-chat"
  location                    = var.GCP_REGION
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    environment = "stg"
    project     = "hit8"
    managed_by  = "terraform"
    purpose     = "chat-documents"
  }

  autoclass {
    enabled = true
  }
  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }
}

# Knowledge Storage (Dev)
resource "google_storage_bucket" "knowledge_dev" {
  name                        = "${var.GCP_PROJECT_ID}-dev-knowledge"
  location                    = var.GCP_REGION
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    environment = "dev"
    project     = "hit8"
    managed_by  = "terraform"
    purpose     = "knowledge"
  }

  autoclass {
    enabled = true
  }
  # No lifecycle rule - knowledge buckets are long-term storage
}

# Knowledge Storage (Stg)
resource "google_storage_bucket" "knowledge_stg" {
  name                        = "${var.GCP_PROJECT_ID}-stg-knowledge"
  location                    = var.GCP_REGION
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    environment = "stg"
    project     = "hit8"
    managed_by  = "terraform"
    purpose     = "knowledge"
  }

  autoclass {
    enabled = true
  }
  # No lifecycle rule - knowledge buckets are long-term storage
}

# Knowledge Storage (Prd)
resource "google_storage_bucket" "knowledge_prd" {
  name                        = "${var.GCP_PROJECT_ID}-prd-knowledge"
  location                    = var.GCP_REGION
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    environment = "prd"
    project     = "hit8"
    managed_by  = "terraform"
    purpose     = "knowledge"
  }

  autoclass {
    enabled = true
  }
  # No lifecycle rule - knowledge buckets are long-term storage
}

# Function Source Code
resource "google_storage_bucket" "function_source" {
  name                        = "${var.GCP_PROJECT_ID}-functions"
  location                    = var.GCP_REGION
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true

  labels = {
    project    = "hit8"
    managed_by = "terraform"
    purpose    = "functions-source"
  }

  autoclass {
    enabled = true
  }
  lifecycle_rule {
    condition { age = 30 }
    action { type = "Delete" }
  }
}

# Terraform State Bucket
# This bucket is cross-environment and stores Terraform state for all environments (prd, stg, dev)
# The name includes "prd" for historical reasons, but it's shared across all environments
# Note: Autoclass is NOT enabled for this bucket as Terraform state files are accessed frequently
resource "google_storage_bucket" "terraform_state" {
  name                        = "hit8-poc-prd-tfstate"
  location                    = var.GCP_REGION # Single Region
  storage_class               = "STANDARD"     # Regional Class
  force_destroy               = false
  uniform_bucket_level_access = true

  labels = {
    project    = "hit8"
    managed_by = "terraform"
    purpose    = "terraform-state"
  }

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
  project = var.GCP_PROJECT_ID
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.vertex_sa.email}"
}

# API Runner Service Account
resource "google_service_account" "api_runner" {
  account_id   = "api-runner-sa"
  display_name = "Cloud Run API Service Account"
  description  = "Dedicated identity for the API service"
}

# Doppler token secrets: store only the Doppler service token (not full JSON).
# Containers use `doppler run` to fetch secrets at runtime. Populate with:
#   echo -n "<doppler-service-token>" | gcloud secrets versions add doppler-token-prd --data-file=-
resource "google_secret_manager_secret" "doppler_token_prd" {
  secret_id = "doppler-token-prd"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "doppler_token_stg" {
  secret_id = "doppler-token-stg"
  replication {
    auto {}
  }
}

# Initial secret version so "latest" exists; Cloud Run requires it. Replace with real token:
#   echo -n "<doppler-service-token>" | gcloud secrets versions add doppler-token-prd --data-file=-
#   echo -n "<doppler-service-token>" | gcloud secrets versions add doppler-token-stg --data-file=-
resource "google_secret_manager_secret_version" "doppler_token_prd" {
  secret      = google_secret_manager_secret.doppler_token_prd.id
  secret_data = "replace-with-real-doppler-token"
}

resource "google_secret_manager_secret_version" "doppler_token_stg" {
  secret      = google_secret_manager_secret.doppler_token_stg.id
  secret_data = "replace-with-real-doppler-token"
}

# Grant Cloud Run service account access to Doppler token secrets
resource "google_secret_manager_secret_iam_member" "api_doppler_token_access" {
  for_each = local.envs

  secret_id = each.key == "prd" ? google_secret_manager_secret.doppler_token_prd.id : google_secret_manager_secret.doppler_token_stg.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_runner.email}"
}

# ==============================================================================
# COMPUTE
# ==============================================================================
# Cloud Run Service
resource "google_cloud_run_v2_service" "api" {
  for_each = local.envs

  name     = "hit8-api${each.value.suffix}" # hit8-api-prd / hit8-api-stg
  location = var.GCP_REGION

  labels = {
    environment = each.key
    project     = "hit8"
    managed_by  = "terraform"
  }

  # Image tags are managed by CI/CD, not Terraform
  # CI/CD updates services after building new images
  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }

  template {
    service_account = google_service_account.api_runner.email
    timeout         = "300s"

    containers {
      # Initial image reference (CI/CD will update this after each build)
      image = "${var.GCP_REGION}-docker.pkg.dev/${var.GCP_PROJECT_ID}/${var.ARTIFACT_REGISTRY_REPOSITORY}/api:${local.image_version}"

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
        name  = "DOPPLER_PROJECT"
        value = "hit8"
      }

      env {
        name  = "DOPPLER_CONFIG"
        value = each.key # prd / stg
      }

      env {
        name  = "BACKEND_PROVIDER"
        value = "gcp"
      }

      env {
        name = "DOPPLER_TOKEN"
        value_source {
          secret_key_ref {
            secret  = each.value.token_secret_id
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
      max_instance_count = 10
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
    google_secret_manager_secret_iam_member.api_doppler_token_access
  ]
}

# Allow Public Access
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  for_each = google_cloud_run_v2_service.api

  project  = var.GCP_PROJECT_ID
  location = each.value.location
  name     = each.value.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Domain Mapping
resource "google_cloud_run_domain_mapping" "api" {
  for_each = local.envs

  name     = "${each.value.host}.hit8.io" # api-prd.hit8.io / api-stg.hit8.io
  location = var.GCP_REGION
  metadata { namespace = var.GCP_PROJECT_ID }

  spec {
    route_name = google_cloud_run_v2_service.api[each.key].name
  }

  depends_on = [google_cloud_run_v2_service.api]
}

# ==============================================================================
# CLOUD RUN JOB (Now Deploying Prd & Stg)
# ==============================================================================
resource "google_cloud_run_v2_job" "report_job" {
  for_each = local.envs # <--- LOOP ENABLED

  name                = "hit8-report-job${each.value.suffix}" # hit8-report-job-prd / -stg
  location            = var.GCP_REGION
  deletion_protection = true

  labels = {
    environment = each.key
    project     = "hit8"
    managed_by  = "terraform"
  }

  # Image tags are managed by CI/CD, not Terraform
  # CI/CD updates jobs after building new images
  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image
    ]
  }

  template {
    template {
      service_account = google_service_account.api_runner.email

      containers {
        # Container name is required for ContainerOverride to work correctly
        name = "api"

        # Initial image reference (CI/CD will update this after each build)
        image = "${var.GCP_REGION}-docker.pkg.dev/${var.GCP_PROJECT_ID}/${var.ARTIFACT_REGISTRY_REPOSITORY}/api:${local.image_version}"

        command = ["/usr/local/bin/python", "-u", "-m", "app.batch.run_report_job"]

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

        env {
          name  = "DOPPLER_PROJECT"
          value = "hit8"
        }

        env {
          name  = "DOPPLER_CONFIG"
          value = each.key # prd / stg
        }

        env {
          name  = "BACKEND_PROVIDER"
          value = "gcp"
        }

        env {
          name = "DOPPLER_TOKEN"
          value_source {
            secret_key_ref {
              secret  = each.value.token_secret_id
              version = "latest"
            }
          }
        }
      }

      timeout     = "3600s"
      max_retries = 2

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
  depends_on = [google_secret_manager_secret_iam_member.api_doppler_token_access]
}

# ==============================================================================
# JOB IAM (Allow API SA to run Cloud Run jobs)
# ==============================================================================
# Grant permission to api_runner service account (used by Cloud Run service)
resource "google_cloud_run_v2_job_iam_member" "api_jobs_runner" {
  for_each = google_cloud_run_v2_job.report_job # <--- LOOP OVER JOBS

  project  = var.GCP_PROJECT_ID
  location = var.GCP_REGION
  name     = each.value.name
  role     = "roles/run.developer" # Required to run Cloud Run v2 jobs (includes run.jobs.run permission)
  member   = "serviceAccount:${google_service_account.api_runner.email}"
}

# Grant permission to vertex service account (used for API client authentication)
resource "google_cloud_run_v2_job_iam_member" "vertex_jobs_runner" {
  for_each = google_cloud_run_v2_job.report_job # <--- LOOP OVER JOBS

  project  = var.GCP_PROJECT_ID
  location = var.GCP_REGION
  name     = each.value.name
  role     = "roles/run.developer" # Required to run Cloud Run v2 jobs (includes run.jobs.run permission)
  member   = "serviceAccount:${google_service_account.vertex_sa.email}"
}

# ==============================================================================
# FUNCTIONS
# ==============================================================================
# Enable Identity Platform API
resource "google_project_service" "identity_platform" {
  provider = google-beta
  project  = var.GCP_PROJECT_ID
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
  project  = var.GCP_PROJECT_ID

  depends_on = [google_project_service.identity_platform]
}

# Deploy Gen 1 Function
resource "google_cloudfunctions_function" "on_before_user_created" {
  name        = "onBeforeUserCreated-v2"
  description = "Firebase Auth blocking hook"
  runtime     = "nodejs20"
  region      = var.GCP_REGION

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
  project        = var.GCP_PROJECT_ID
  region         = var.GCP_REGION
  cloud_function = google_cloudfunctions_function.on_before_user_created.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_project_service_identity.identity_platform_agent.email}"
}

# Configure Identity Platform to use the blocking function
resource "google_identity_platform_config" "auth_config" {
  provider = google-beta
  project  = var.GCP_PROJECT_ID

  # Authorized domains for OAuth operations
  authorized_domains = [
    "localhost",
    "www.hit8.io",
    "hit8.io",
    "hit8.pages.dev",
    "main-staging.hit8.pages.dev",
    "hit8-poc.firebaseapp.com",
    "hit8-poc.web.app",
  ]

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

# API Runner Access - Knowledge Buckets
resource "google_storage_bucket_iam_member" "api_knowledge_access_dev" {
  bucket = google_storage_bucket.knowledge_dev.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

resource "google_storage_bucket_iam_member" "api_knowledge_access_stg" {
  bucket = google_storage_bucket.knowledge_stg.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

resource "google_storage_bucket_iam_member" "api_knowledge_access_prd" {
  bucket = google_storage_bucket.knowledge_prd.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api_runner.email}"
}

# Vertex SA Access - Knowledge Buckets
resource "google_storage_bucket_iam_member" "vertex_knowledge_access_dev" {
  bucket = google_storage_bucket.knowledge_dev.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vertex_sa.email}"
}

resource "google_storage_bucket_iam_member" "vertex_knowledge_access_stg" {
  bucket = google_storage_bucket.knowledge_stg.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vertex_sa.email}"
}

resource "google_storage_bucket_iam_member" "vertex_knowledge_access_prd" {
  bucket = google_storage_bucket.knowledge_prd.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.vertex_sa.email}"
}
