terraform {
  backend "gcs" {
    bucket = "hit8-poc-prd-tfstate"
    prefix = "terraform/state"
  }
}

