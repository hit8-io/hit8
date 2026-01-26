################################################################################
#                                  DNS RECORDS                                 #
################################################################################

resource "cloudflare_record" "services" {
  for_each = {
    "langfuse" = "8e1e99a0-9f3f-4c30-90da-2cc2d18b9f94.cfargotunnel.com"
    "n8n"      = "8e1e99a0-9f3f-4c30-90da-2cc2d18b9f94.cfargotunnel.com"
    "neo4j"    = "8e1e99a0-9f3f-4c30-90da-2cc2d18b9f94.cfargotunnel.com"
    "traefik"  = "8e1e99a0-9f3f-4c30-90da-2cc2d18b9f94.cfargotunnel.com"
    "www"      = "hit8.pages.dev"
  }

  zone_id = var.cloudflare_zone_id
  name    = each.key
  content = each.value
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

resource "cloudflare_record" "api_endpoints" {
  for_each = local.envs

  zone_id = var.cloudflare_zone_id
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
  zone_id = var.cloudflare_zone_id
  name    = var.domain_name
  content = "hit8.pages.dev"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

# Dummy A record for chat subdomain - actual routing handled by redirect ruleset
resource "cloudflare_record" "chat_dummy" {
  zone_id = var.cloudflare_zone_id
  name    = "chat"
  content = "192.0.2.1" # RFC 3330 documentation address
  type    = "A"
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

  zone_id  = var.cloudflare_zone_id
  name     = var.domain_name
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

  zone_id = var.cloudflare_zone_id
  name    = var.domain_name
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

  zone_id = var.cloudflare_zone_id
  name    = each.key
  content = each.value
  type    = "CNAME"
  proxied = false
  ttl     = 1
}

################################################################################
#                             RULESETS & REDIRECTS                             #
################################################################################

resource "cloudflare_ruleset" "cache_settings" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_cache_settings"
  zone_id = var.cloudflare_zone_id

  rules {
    description = "Bypass Cache for Chat"
    enabled     = true
    expression  = "(http.request.full_uri contains \"chat.hit8.io\")"
    action      = "set_cache_settings"
    action_parameters {
      cache = false
    }
  }
}

resource "cloudflare_ruleset" "redirects" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_dynamic_redirect"
  zone_id = var.cloudflare_zone_id

  rules {
    description = "chat.hit8.io Redirect"
    enabled     = true
    expression  = "(http.request.full_uri contains \"chat.hit8.io\")"
    action      = "redirect"
    action_parameters {
      from_value {
        status_code           = 302
        preserve_query_string = true
        target_url {
          value = var.chat_webhook_url
        }
      }
    }
  }

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

resource "cloudflare_ruleset" "waf_custom" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_firewall_custom"
  zone_id = var.cloudflare_zone_id

  # Block direct API access - only allow requests from our frontend (hit8.pages.dev) and www.hit8.io
  # This prevents unauthorized direct API calls while allowing legitimate frontend requests
  rules {
    description = "Block Direct API Access"
    enabled     = true
    expression  = "((http.host eq \"api-prd.hit8.io\" or http.host eq \"api-stg.hit8.io\") and not http.referer contains \"hit8.pages.dev\" and not http.referer contains \"www.hit8.io\")"
    action      = "block"
  }
}

################################################################################
#                            SETTINGS & ACCOUNT                                #
################################################################################

resource "cloudflare_zone_settings_override" "main_settings" {
  zone_id = var.cloudflare_zone_id

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

resource "cloudflare_pages_project" "hit8" {
  account_id        = var.cloudflare_account_id
  name              = "hit8"
  production_branch = "main"

  source {
    type = "github"
    config {
      owner                         = "hit8-io"
      repo_name                     = "hit8"
      production_branch             = "main"
      pr_comments_enabled           = true
      deployments_enabled           = true
      production_deployment_enabled = true
      preview_deployment_setting    = "all"
      preview_branch_includes       = ["*"]
      preview_branch_excludes       = []
    }
  }

  build_config {
    build_command   = "cd frontend && npm ci && npm run build"
    destination_dir = "frontend/dist"
    root_dir        = "/"
  }
}

resource "cloudflare_account_member" "admin" {
  account_id    = var.cloudflare_account_id
  email_address = "jan@hit8.io"
  role_ids      = ["33666b9c79b9a5273fc7344ff42f953d"]
  status        = "accepted"
}
