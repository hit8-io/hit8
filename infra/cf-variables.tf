variable "CLOUDFLARE_ACCOUNT_ID" {
  description = "Cloudflare Account ID"
  type        = string
  sensitive   = true
}

variable "CLOUDFLARE_ZONE_ID" {
  description = "Zone ID for hit8.io"
  type        = string
  sensitive   = true
}

variable "DOMAIN_NAME" {
  description = "Root domain name"
  type        = string
  default     = "hit8.io"
}
