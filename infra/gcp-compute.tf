locals {
  # Assumes VERSION file is in the root (where you run terraform) or parent
  # Adjust path as needed: "${path.module}/../VERSION"
  image_version = trimspace(file("${path.module}/../VERSION"))
}

# ==============================================================================
# CLOUD RUN SERVICE
# ==============================================================================
resource "google_cloud_run_v2_service" "api" {
  name     = var.service_name # Uses "hit8-api"
  location = var.region
  
  template {
    service_account = google_service_account.api_runner.email
    timeout         = "300s"
    
    containers {
      # Interpolates "backend" from var.artifact_registry_repository
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_registry_repository}/api:${local.image_version}"
      
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

# Allow Public Access
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==============================================================================
# DOMAIN MAPPING
# ==============================================================================
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
# CLOUD RUN JOB
# ==============================================================================
resource "google_cloud_run_v2_job" "report_job" {
  name               = "hit8-report-job"
  location           = var.region
  deletion_protection = true  # Enabled for production safety

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
