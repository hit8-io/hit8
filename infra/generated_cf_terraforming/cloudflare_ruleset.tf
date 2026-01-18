resource "cloudflare_ruleset" "terraform_managed_resource_f01dc97f1a954fe8adc3f4f2ffc8b648_0" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_cache_settings"
  zone_id = "12913dce4b9e34176e2f2b2f1ed3386a"
  rules {
    action = "set_cache_settings"
    action_parameters {
      cache = false
    }
    description = "chat.hit8.io"
    enabled     = true
    expression  = "(http.request.full_uri contains \"chat.hit8.io\")"
  }
}

resource "cloudflare_ruleset" "terraform_managed_resource_63ef218284f442f195eb583711fca4f7_1" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_dynamic_redirect"
  zone_id = "12913dce4b9e34176e2f2b2f1ed3386a"
  rules {
    action = "redirect"
    action_parameters {
      from_value {
        preserve_query_string = true
        status_code           = 302
        target_url {
          value = "https://n8n.hit8.io/webhook/3f002629-381b-4036-bd14-bda894ebb6db/chat"
        }
      }
    }
    description = "chat.hit8.io"
    enabled     = true
    expression  = "(http.request.full_uri contains \"chat.hit8.io\")"
  }
  rules {
    action = "redirect"
    action_parameters {
      from_value {
        preserve_query_string = true
        status_code           = 301
        target_url {
          expression = "concat(\"https://www.hit8.io\", http.request.uri.path)"
        }
      }
    }
    description = "Root to WWW"
    enabled     = true
    expression  = "(http.host eq \"hit8.io\")"
  }
}

resource "cloudflare_ruleset" "terraform_managed_resource_c28974b3a25f44de983fa7a325f45ebb_2" {
  kind    = "zone"
  name    = "default"
  phase   = "http_request_firewall_custom"
  zone_id = "12913dce4b9e34176e2f2b2f1ed3386a"
  rules {
    action      = "block"
    description = "Cloudfare Pages -> api.hit8.io"
    enabled     = true
    expression  = "(http.host eq \"api.hit8.io\" and not http.referer contains \"hit8.pages.dev\" and not http.referer contains \"www.hit8.io\")"
  }
}

