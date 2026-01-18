# ==============================================================================
# ARTIFACT REGISTRY
# ==============================================================================
resource "google_artifact_registry_repository" "backend_api" {
  location      = var.region
  repository_id = var.artifact_registry_repository # Uses "backend"
  description   = "Docker repository for backend API"
  format        = "DOCKER"
}

# ==============================================================================
# BUCKETS
# ==============================================================================
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

# Function Source Code
resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-prd-functions"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  lifecycle_rule {
    condition { age = 30 }
    action { type = "Delete" }
  }
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
