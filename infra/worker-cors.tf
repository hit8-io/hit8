################################################################################
# Worker: CORS preflight (OPTIONS) for API hostnames
################################################################################
# Responds to OPTIONS with 200 + CORS headers so preflight always gets 2xx.
# All other methods are forwarded to the origin. When backend is Scaleway,
# fetches the Scaleway container URL directly to avoid same-zone fetch 404.
#
# API token permissions required (or use "Edit Cloudflare Workers" template):
#   Account → Workers Scripts → Edit
#   Zone    → Workers Routes  → Edit   (select hit8.io zone)
# Routes are zone-scoped; Scripts are account-scoped.
################################################################################

locals {
  worker_script_content = templatefile("${path.module}/workers/api-cors-preflight.js.tpl", { origin_map_json = local.worker_origin_map_json })
}

resource "cloudflare_workers_script" "api_cors_preflight" {
  account_id     = var.CLOUDFLARE_ACCOUNT_ID
  script_name    = "api-cors-preflight"
  content        = local.worker_script_content
  content_sha256 = sha256(local.worker_script_content)
}

resource "cloudflare_workers_route" "api_cors_preflight" {
  for_each = toset(local.api_hosts)
  zone_id  = var.CLOUDFLARE_ZONE_ID
  pattern  = "${each.value}/*"
  script   = cloudflare_workers_script.api_cors_preflight.script_name
}
