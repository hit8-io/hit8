################################################################################
#                                  DNS RECORDS                                 #
################################################################################

resource "cloudflare_record" "services" {
  for_each = {
    "www"   = "hit8-site.pages.dev" # Changed: marketing site
    "iter8" = "hit8.pages.dev"      # New: SaaS app
    "scw"   = "hit8.pages.dev"      # Unchanged: SaaS app Scaleway variant
  }

  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = each.key
  content = each.value
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# Scaleway containers (scw-prd, scw-stg) - CNAME targets from Scaleway container domain setup
# Commented out until containers are created (after images are built and pushed)
# resource "cloudflare_record" "scw_api" {
#   for_each = {
#     "scw-prd" = scaleway_container_domain.prd.url
#     "scw-stg" = scaleway_container_domain.stg.url
#   }
#
#   zone_id = var.CLOUDFLARE_ZONE_ID
#   name    = each.key
#   content = each.value
#   type    = "CNAME"
#   proxied = true
#   ttl     = 1
# }

resource "cloudflare_record" "api_endpoints" {
  for_each = local.envs

  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = each.value.host # api-prd / api-stg
  content = "ghs.googlehosted.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}


# Dummy A record for root domain - actual routing handled by redirect ruleset
# Root domain CNAME record pointing to Cloudflare Pages
# This record was imported from existing Cloudflare configuration
resource "cloudflare_record" "root" {
  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = var.DOMAIN_NAME
  content = "hit8-site.pages.dev" # Changed: marketing site
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

resource "cloudflare_record" "mx_records" {
  for_each = {
    "aspmx.l.google.com"      = 1
    "alt1.aspmx.l.google.com" = 5
    "alt2.aspmx.l.google.com" = 5
    "alt3.aspmx.l.google.com" = 10
    "alt4.aspmx.l.google.com" = 10
  }

  zone_id  = var.CLOUDFLARE_ZONE_ID
  name     = var.DOMAIN_NAME
  content  = each.key
  priority = each.value
  type     = "MX"
  proxied  = false
  ttl      = 1
}

resource "cloudflare_record" "txt_records" {
  for_each = {
    "spf"      = "v=spf1 include:_spf.firebasemail.com ~all"
    "firebase" = "firebase=hit8-poc"
  }

  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = var.DOMAIN_NAME
  content = each.value
  type    = "TXT"
  proxied = false
  ttl     = 1
}

resource "cloudflare_record" "firebase_dkim" {
  for_each = {
    "firebase1._domainkey" = "mail-hit8-io.dkim1._domainkey.firebasemail.com."
    "firebase2._domainkey" = "mail-hit8-io.dkim2._domainkey.firebasemail.com."
  }

  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = each.key
  content = each.value
  type    = "CNAME"
  proxied = false
  ttl     = 1
}

################################################################################
#                             RULESETS & REDIRECTS                             #
################################################################################

resource "cloudflare_ruleset" "redirects" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_dynamic_redirect"
  zone_id = var.CLOUDFLARE_ZONE_ID

  rules {
    description = "Root to WWW"
    enabled     = true
    expression  = "(http.host eq \"hit8.io\")"
    action      = "redirect"
    action_parameters {
      from_value {
        status_code           = 301
        preserve_query_string = true
        target_url {
          expression = "concat(\"https://www.hit8.io\", http.request.uri.path)"
        }
      }
    }
  }
}

################################################################################
#                            WAF CUSTOM RULES                                   #
################################################################################

resource "cloudflare_ruleset" "waf_custom" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_firewall_custom"
  zone_id = var.CLOUDFLARE_ZONE_ID

  rules {
    description = "Block Direct API Access"
    enabled     = true
    expression  = "((http.host eq \"api-prd.hit8.io\" or http.host eq \"api-stg.hit8.io\" or http.host eq \"scw-prd.hit8.io\" or http.host eq \"scw-stg.hit8.io\") and not http.referer contains \"hit8.pages.dev\" and not http.referer contains \"hit8-site.pages.dev\" and not http.referer contains \"www.hit8.io\" and not http.referer contains \"iter8.hit8.io\" and not http.referer contains \"scw.hit8.io\")"
    action      = "block"
  }
}

################################################################################
#                            RATE LIMITING                                      #
################################################################################

resource "cloudflare_ruleset" "rate_limit" {
  kind    = "zone"
  name    = "rate_limiting"
  phase   = "http_ratelimit"
  zone_id = var.CLOUDFLARE_ZONE_ID

  # Cloudflare only allows 1 rule in http_ratelimit phase
  # Using a single rule with 20 req/10s limit (120 req/min) for all API endpoints
  # Note: Cloudflare free plan only supports period=10 (10 seconds)
  rules {
    description = "Rate Limit API Endpoints"
    enabled     = true
    expression  = "(http.host in {\"api-prd.hit8.io\" \"api-stg.hit8.io\" \"scw-prd.hit8.io\" \"scw-stg.hit8.io\"})"
    action      = "block"

    action_parameters {
      response {
        status_code  = 429
        content      = "{\"error\": \"Rate limit exceeded. Maximum 20 requests per 10 seconds.\"}"
        content_type = "application/json"
      }
    }

    ratelimit {
      characteristics     = ["ip.src", "cf.colo.id"]
      period              = 10
      requests_per_period = 20
      mitigation_timeout  = 10
    }
  }
}

################################################################################
#                            SETTINGS & ACCOUNT                                #
################################################################################

resource "cloudflare_zone_settings_override" "main_settings" {
  zone_id = var.CLOUDFLARE_ZONE_ID

  settings {
    # SSL / Security
    ssl                      = "strict"
    min_tls_version          = "1.2"
    always_use_https         = "on"
    automatic_https_rewrites = "on"

    # Performance
    brotli           = "on"
    http3            = "on"
    always_online    = "off"
    development_mode = "off"

    # Network
    ipv6                     = "on"
    websockets               = "on"
    opportunistic_encryption = "on"

    # Privacy / Other
    email_obfuscation = "on"
    security_level    = "medium"
  }
}

# Pages project: Direct Upload (Wrangler). API rejects source/build_config updates.
resource "cloudflare_pages_project" "hit8" {
  account_id        = var.CLOUDFLARE_ACCOUNT_ID
  name              = "hit8"
  production_branch = "main"

  lifecycle {
    ignore_changes = [source, build_config]
  }

  build_config {
    build_command   = ""
    destination_dir = ""
  }

  deployment_configs {
    production {
      environment_variables = {
        VITE_API_URL = "https://api-prd.hit8.io"
      }
      compatibility_date = "2024-01-01"
    }
    preview {
      environment_variables = {
        VITE_API_URL = "https://scw-stg.hit8.io"
      }
      compatibility_date = "2024-01-01"
    }
  }
}

# Marketing site Pages project
resource "cloudflare_pages_project" "hit8_site" {
  account_id        = var.CLOUDFLARE_ACCOUNT_ID
  name              = "hit8-site"
  production_branch = "main"

  lifecycle {
    ignore_changes = [source, build_config]
  }

  build_config {
    build_command   = ""
    destination_dir = ""
  }

  deployment_configs {
    production {
      environment_variables = {}
      compatibility_date    = "2024-01-01"
    }
    preview {
      environment_variables = {}
      compatibility_date    = "2024-01-01"
    }
  }
}

# Custom domain for marketing site
resource "cloudflare_pages_domain" "www" {
  account_id   = var.CLOUDFLARE_ACCOUNT_ID
  project_name = cloudflare_pages_project.hit8_site.name
  domain       = "www.${var.DOMAIN_NAME}"
}

# Update existing hit8 project domain
resource "cloudflare_pages_domain" "iter8" {
  account_id   = var.CLOUDFLARE_ACCOUNT_ID
  project_name = cloudflare_pages_project.hit8.name
  domain       = "iter8.${var.DOMAIN_NAME}"
}

# scw.hit8.io: same frontend as iter8, but backend scw-prd.hit8.io
# Requires frontend to detect host: if host === "scw.hit8.io" then API = "https://scw-prd.hit8.io"
resource "cloudflare_pages_domain" "scw" {
  account_id   = var.CLOUDFLARE_ACCOUNT_ID
  project_name = cloudflare_pages_project.hit8.name
  domain       = "scw.${var.DOMAIN_NAME}"
}

resource "cloudflare_account_member" "admin" {
  account_id    = var.CLOUDFLARE_ACCOUNT_ID
  email_address = "jan@hit8.io"
  role_ids      = ["33666b9c79b9a5273fc7344ff42f953d"]
  status        = "accepted"
}
