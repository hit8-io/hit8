resource "cloudflare_filter" "terraform_managed_resource_3a2b1804bcf143f4b323e4dcfd389db1_0" {
  expression = "(http.host eq \"api.hit8.io\" and not http.referer contains \"hit8.pages.dev\" and not http.referer contains \"www.hit8.io\")"
  paused     = false
  zone_id    = "12913dce4b9e34176e2f2b2f1ed3386a"
}

