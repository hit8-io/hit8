# 0. Enable Identity Platform API
resource "google_project_service" "identity_platform" {
  provider = google-beta
  project  = var.project_id
  service  = "identitytoolkit.googleapis.com"
  
  disable_on_destroy = false
}

# 1. Package source
data "archive_file" "on_before_user_created_source" {
  type        = "zip"
  source_dir  = "${path.module}/functions/onBeforeUserCreated-v2"
  output_path = "${path.module}/functions/onBeforeUserCreated-v2.zip"
}

# 2. Upload source
resource "google_storage_bucket_object" "on_before_user_created_source" {
  name   = "onBeforeUserCreated-v2-${data.archive_file.on_before_user_created_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.on_before_user_created_source.output_path
}

# 3. Lookup Identity Platform Service Agent
resource "google_project_service_identity" "identity_platform_agent" {
  provider = google-beta
  service  = "identitytoolkit.googleapis.com"
  project  = var.project_id
  
  depends_on = [google_project_service.identity_platform]
}

# 4. Deploy Gen 1 Function
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

# 5. SECURE IAM: Allow ONLY Identity Platform to invoke
resource "google_cloudfunctions_function_iam_member" "identity_platform_invoker" {
  project        = var.project_id
  region         = var.region
  cloud_function = google_cloudfunctions_function.on_before_user_created.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${google_project_service_identity.identity_platform_agent.email}"
}

# 6. Configure Identity Platform to use the blocking function
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
