data "hcl_schema" "hit8" {
  paths = fileset("schemas/**/*.hcl")
}

env "dev" {
  src = data.hcl_schema.hit8.url
  url = "postgresql://postgres:postgres@localhost:54325/postgres?sslmode=disable&search_path=hit8"
}

env "stg" {
  src = data.hcl_schema.hit8.url
  url = "${getenv("DIRECT_DB_CONNECTION_STRING")}&search_path=hit8"
}

env "prd" {
  src = data.hcl_schema.hit8.url
  url = "${getenv("DIRECT_DB_CONNECTION_STRING")}&search_path=hit8"
}
