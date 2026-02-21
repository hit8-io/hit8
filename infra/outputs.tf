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
output "scw_api_urls" {
  value = {
    prd = "https://${scaleway_container_domain.prd.hostname}"
    stg = "https://${scaleway_container_domain.stg.hostname}"
  }
  description = "Scaleway Container API URLs"
}

output "scw_registry_endpoint" {
  value       = scaleway_registry_namespace.main.endpoint
  description = "Scaleway Docker registry endpoint"
}

output "prd_bastion_ipv6" {
  value       = scaleway_instance_ip.prd_bastion_ipv6.address
  description = "Production bastion VM public IPv6 address (for admin SSH + psql to managed DB)"
}

output "prd_bastion_ssh_command" {
  value       = "ssh root@${scaleway_instance_ip.prd_bastion_ipv6.address}"
  description = "SSH into production bastion (hit8-prd-bastion)"
}

output "stg_vm_ipv6" {
  value       = scaleway_instance_ip.stg_vm_ipv6.address
  description = "Staging VM public IPv6 address (hit8-stg-vm)"
}

output "stg_ssh_command" {
  value       = "ssh root@${scaleway_instance_ip.stg_vm_ipv6.address}"
  description = "SSH into staging VM (hit8-stg-vm)"
}

output "prd_db_admin_example" {
  value = {
    bastion_ssh       = "ssh root@${scaleway_instance_ip.prd_bastion_ipv6.address}"
    db_private_ip     = scaleway_rdb_instance.prd_db.private_network[0].ip
    psql_from_bastion = "psql -h ${scaleway_rdb_instance.prd_db.private_network[0].ip} -U hit8 -p 5432"
    note              = "Connect via bastion IPv6 → private network to DB. Remove public LB endpoint to save costs."
  }
}

# Cloudflare (Zone ID — useful for API/CLI; name servers are in console)
output "cloudflare_zone_name_servers" {
  value       = var.CLOUDFLARE_ZONE_ID
  description = "Cloudflare Zone ID for hit8.io"
  sensitive   = true
}

