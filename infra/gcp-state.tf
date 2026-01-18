# ==============================================================================
# TERRAFORM STATE BUCKET
# ==============================================================================
# This bucket stores Terraform state files

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
