packer {
  required_plugins {
    googlecompute = {
      source  = "github.com/hashicorp/googlecompute"
      version = "~> 1.0"
    }
  }
}

variable "project_id" {
  type    = string
  default = "hit8-poc" # Your Project ID
}

variable "zone" {
  type    = string
  default = "europe-west1-b"
}

source "googlecompute" "proxy_image" {
  project_id   = var.project_id
  source_image_family = "debian-12"
  zone         = var.zone
  ssh_username = "packer"
  machine_type = "e2-medium" # Faster build
  
  # The Resulting Image Name
  image_name        = "proxy-gateway-v1-{{timestamp}}"
  image_description = "Squid and Dante proxy pre-baked"
  image_family      = "proxy-gateway"
}

build {
  sources = ["sources.googlecompute.proxy_image"]

  # Upload the setup script
  provisioner "shell" {
    script = "setup.sh"
    execute_command = "sudo -S sh -c '{{ .Vars }} {{ .Path }}'"
  }
}
