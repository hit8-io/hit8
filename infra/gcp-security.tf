# ==============================================================================
# 1. VERTEX AI SERVICE ACCOUNT (Existing)
# ==============================================================================
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

# ==============================================================================
# 2. API RUNNER SERVICE ACCOUNT (New)
# ==============================================================================
resource "google_service_account" "api_runner" {
  account_id   = "api-runner-sa"
  display_name = "Cloud Run API Service Account"
  description  = "Dedicated identity for the API service"
}

# Grant Secret Access to API Runner
resource "google_secret_manager_secret_iam_member" "api_secret_access" {
  secret_id = google_secret_manager_secret.doppler_secrets.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_runner.email}"
  
  depends_on = [google_secret_manager_secret.doppler_secrets]
}

# ==============================================================================
# 3. SECRETS
# ==============================================================================
resource "google_secret_manager_secret" "doppler_secrets" {
  secret_id = var.secret_name # Uses "doppler-hit8-prod"
  replication {
    auto {}
  }
}
