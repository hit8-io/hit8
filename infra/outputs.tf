# ==============================================================================
# OUTPUTS — operational visibility
# ==============================================================================

# GCP
output "gcp_api_urls" {
  value       = { for k, v in google_cloud_run_v2_service.api : k => v.uri }
  description = "GCP Cloud Run API URLs (prd/stg)"
}

output "gcp_static_egress_ip" {
  value       = google_compute_address.egress_ip.address
  description = "Shared static egress IP for GCP (for allowlisting)"
}

# Scaleway
# Commented out until containers are created (after images are built and pushed)
# output "scw_api_urls" {
#   value = {
#     prd = "https://${scaleway_container_domain.prd.hostname}"
#     stg = "https://${scaleway_container_domain.stg.hostname}"
#   }
#   description = "Scaleway Container API URLs"
# }

output "scw_registry_endpoint" {
  value       = scaleway_registry_namespace.main.endpoint
  description = "Scaleway Docker registry endpoint"
}

# Cloudflare (Zone ID — useful for API/CLI; name servers are in console)
output "cloudflare_zone_name_servers" {
  value       = var.CLOUDFLARE_ZONE_ID
  description = "Cloudflare Zone ID for hit8.io"
  sensitive   = true
}
