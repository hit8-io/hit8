################################################################################
# Worker: CORS preflight (OPTIONS) for API hostnames
################################################################################
# Responds to OPTIONS with 200 + CORS headers so preflight always gets 2xx.
# All other methods are forwarded to the origin.
#
# API token permissions required (or use "Edit Cloudflare Workers" template):
#   Account → Workers Scripts → Edit
#   Zone    → Workers Routes  → Edit   (select hit8.io zone)
# Routes are zone-scoped; Scripts are account-scoped.
################################################################################

resource "cloudflare_workers_script" "api_cors_preflight" {
  account_id     = var.CLOUDFLARE_ACCOUNT_ID
  script_name    = "api-cors-preflight"
  content_file   = "${path.module}/workers/api-cors-preflight.js"
  content_sha256 = filesha256("${path.module}/workers/api-cors-preflight.js")
}

resource "cloudflare_workers_route" "api_cors_preflight" {
  for_each = toset(local.api_hosts)
  zone_id  = var.CLOUDFLARE_ZONE_ID
  pattern  = "${each.value}/*"
  script   = cloudflare_workers_script.api_cors_preflight.script_name
}
