################################################################################
#                                  DNS RECORDS                                 #
################################################################################

# api_hosts_in is derived from backend_provider: only the current provider's hostnames are included.
# So with backend_provider = "scw", WAF and rate limit apply only to scw-prd/scw-stg; gcp-prd/gcp-stg
# are not matched. That is why CORS worked when the frontend used GCP (gcp-prd) and broke when
# it used Scaleway (scw-prd)—the WAF and rate limit only apply to the active provider's hosts.
locals {
  api_url_prd  = var.backend_provider == "gcp" ? "https://gcp-prd.${var.DOMAIN_NAME}" : "https://scw-prd.${var.DOMAIN_NAME}"
  api_url_stg  = var.backend_provider == "gcp" ? "https://gcp-stg.${var.DOMAIN_NAME}" : "https://scw-stg.${var.DOMAIN_NAME}"
  api_hosts    = var.backend_provider == "gcp" ? ["gcp-prd.${var.DOMAIN_NAME}", "gcp-stg.${var.DOMAIN_NAME}"] : ["scw-prd.${var.DOMAIN_NAME}", "scw-stg.${var.DOMAIN_NAME}"]
  api_hosts_in = "(http.host in {\"${join("\" \"", local.api_hosts)}\"})"

  # Scaleway serverless container CNAME targets (exact default domains from Scaleway)
  scw_api_cname_targets = {
    "scw-prd" = var.SCW_CONTAINER_DOMAIN_PRD
    "scw-stg" = var.SCW_CONTAINER_DOMAIN_STG
  }
}

resource "cloudflare_dns_record" "services" {
  for_each = {
    "www"   = "hit8-site.pages.dev"
    "iter8" = "hit8.pages.dev"
  }

  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = "${each.key}.${var.DOMAIN_NAME}"
  content = each.value
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# Scaleway containers (scw-prd, scw-stg) - CNAME to container default domains
resource "cloudflare_dns_record" "scw_api" {
  for_each = local.scw_api_cname_targets

  zone_id  = var.CLOUDFLARE_ZONE_ID
  name     = each.key
  content  = each.value
  type     = "CNAME"
  proxied  = true
  ttl      = 1
}

resource "cloudflare_dns_record" "api_endpoints" {
  for_each = local.envs

  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = "${each.value.host}.${var.DOMAIN_NAME}"
  content = "ghs.googlehosted.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}


# Dummy A record for root domain - actual routing handled by redirect ruleset
# Root domain CNAME record pointing to Cloudflare Pages
# This record was imported from existing Cloudflare configuration
resource "cloudflare_dns_record" "root" {
  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = var.DOMAIN_NAME
  content = "hit8-site.pages.dev" # Changed: marketing site
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

resource "cloudflare_dns_record" "mx_records" {
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

resource "cloudflare_dns_record" "txt_records" {
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

resource "cloudflare_dns_record" "firebase_dkim" {
  for_each = {
    "firebase1._domainkey" = "mail-hit8-io.dkim1._domainkey.firebasemail.com."
    "firebase2._domainkey" = "mail-hit8-io.dkim2._domainkey.firebasemail.com."
  }

  zone_id = var.CLOUDFLARE_ZONE_ID
  name    = "${each.key}.${var.DOMAIN_NAME}"
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

  rules = [
    {
      description = "Root to WWW"
      enabled     = true
      expression  = "(http.host eq \"hit8.io\")"
      action      = "redirect"
      action_parameters = {
        from_value = {
          status_code           = 301
          preserve_query_string = true
          target_url = {
            expression = "concat(\"https://www.hit8.io\", http.request.uri.path)"
          }
        }
      }
    }
  ]
}

################################################################################
#                            WAF CUSTOM RULES                                   #
################################################################################

resource "cloudflare_ruleset" "waf_custom" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_firewall_custom"
  zone_id = var.CLOUDFLARE_ZONE_ID

  rules = [
    {
      description = "Block Direct API Access"
      enabled     = true
      # Block direct API access: API hosts, non-OPTIONS, path not in allowlist, and no allowed Referer.
      # Allowlist (no Referer needed): /health, /version, /debug, /debug/connectivity.
      expression  = "(${local.api_hosts_in} and http.request.method ne \"OPTIONS\" and http.request.uri.path ne \"/health\" and http.request.uri.path ne \"/version\" and http.request.uri.path ne \"/debug\" and http.request.uri.path ne \"/debug/connectivity\" and not http.referer contains \"hit8.pages.dev\" and not http.referer contains \"hit8-site.pages.dev\" and not http.referer contains \"www.${var.DOMAIN_NAME}\" and not http.referer contains \"iter8.${var.DOMAIN_NAME}\")"
      action      = "block"
    }
  ]
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
  # 100 req/10s allows app load (many parallel GETs) + health polling without false 429s.
  # Exclude OPTIONS so CORS preflight is not rate-limited.
  # Note: Cloudflare free plan only supports period=10 (10 seconds)
  rules = [
    {
      description = "Rate Limit API Endpoints"
      enabled     = true
      expression  = "(${local.api_hosts_in} and http.request.method ne \"OPTIONS\")"
      action      = "block"

      action_parameters = {
        response = {
          status_code  = 429
          content      = "{\"error\": \"Rate limit exceeded. Maximum 100 requests per 10 seconds.\"}"
          content_type = "application/json"
        }
      }

      ratelimit = {
        characteristics     = ["ip.src", "cf.colo.id"]
        period              = 10
        requests_per_period  = 100
        mitigation_timeout  = 10
      }
    }
  ]
}

################################################################################
#                            SETTINGS & ACCOUNT                                #
################################################################################

# Zone settings (v5: one resource per setting)
locals {
  zone_settings = {
    # SSL / Security
    ssl                      = "strict"
    min_tls_version          = "1.2"
    always_use_https         = "on"
    automatic_https_rewrites = "on"
    # Performance
    brotli            = "on"
    http3             = "on"
    always_online     = "off"
    development_mode  = "off"
    # Network
    ipv6                      = "on"
    websockets                = "on"
    opportunistic_encryption  = "on"
    # Privacy / Other
    email_obfuscation = "on"
    security_level    = "medium"
  }
}

resource "cloudflare_zone_setting" "main" {
  for_each   = local.zone_settings
  zone_id    = var.CLOUDFLARE_ZONE_ID
  setting_id = each.key
  value      = each.value
}

# Pages project: Direct Upload (Wrangler). API rejects source/build_config updates.
resource "cloudflare_pages_project" "hit8" {
  account_id        = var.CLOUDFLARE_ACCOUNT_ID
  name              = "hit8"
  production_branch = "main"

  lifecycle {
    ignore_changes = [source, build_config]
  }

  build_config = {
    build_command   = ""
    destination_dir = ""
  }

  deployment_configs = {
    production = {
      environment_variables = {
        VITE_API_URL = local.api_url_prd
      }
      compatibility_date = "2024-01-01"
    }
    preview = {
      environment_variables = {
        VITE_API_URL = local.api_url_stg
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

  build_config = {
    build_command   = ""
    destination_dir = ""
  }

  deployment_configs = {
    production = {
      environment_variables = {}
      compatibility_date    = "2024-01-01"
    }
    preview = {
      environment_variables = {}
      compatibility_date    = "2024-01-01"
    }
  }
}

# Custom domain for marketing site.
# Note: Provider schema only has "name"; API may report "missing required domain_name parameter"
# on refresh/destroy—known provider/API mismatch. Run plan/apply with -refresh=false if needed.
# If state still contains cloudflare_pages_domain.scw (removed from config), run:
#   terraform state rm cloudflare_pages_domain.scw
# to avoid the domain_name error on destroy.
resource "cloudflare_pages_domain" "www" {
  account_id   = var.CLOUDFLARE_ACCOUNT_ID
  project_name = cloudflare_pages_project.hit8_site.name
  name         = "www.${var.DOMAIN_NAME}"

  lifecycle {
    ignore_changes = [name]
  }
}

resource "cloudflare_pages_domain" "iter8" {
  account_id   = var.CLOUDFLARE_ACCOUNT_ID
  project_name = cloudflare_pages_project.hit8.name
  name         = "iter8.${var.DOMAIN_NAME}"

  lifecycle {
    ignore_changes = [name]
  }
}

# Account member managed in Cloudflare UI to avoid API "Empty policy assignments" / 403 on update.
# After commenting out: terraform state rm cloudflare_account_member.admin
# resource "cloudflare_account_member" "admin" {
#   account_id = var.CLOUDFLARE_ACCOUNT_ID
#   email      = "jan@hit8.io"
#   roles      = ["33666b9c79b9a5273fc7344ff42f953d"]
#   status     = "accepted"
# }
