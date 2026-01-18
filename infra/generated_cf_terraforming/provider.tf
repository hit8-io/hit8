terraform {
  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}
provider "cloudflare" {
  api_token = "JkcHOjinNVpJkjB9afhUWNICeH4KUruoXTfN_psD"
}
