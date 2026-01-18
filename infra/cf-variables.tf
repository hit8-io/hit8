variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
  type        = string
  default     = "b3264445f09fa6a420e40e424c81e23d"
}

variable "cloudflare_zone_id" {
  description = "Zone ID for hit8.io"
  type        = string
  default     = "12913dce4b9e34176e2f2b2f1ed3386a"
}

variable "domain_name" {
  description = "Root domain name"
  type        = string
  default     = "hit8.io"
}

variable "chat_webhook_url" {
  description = "Target URL for chat redirect (n8n webhook)"
  type        = string
  default     = "https://n8n.hit8.io/webhook/3f002629-381b-4036-bd14-bda894ebb6db/chat"
}
