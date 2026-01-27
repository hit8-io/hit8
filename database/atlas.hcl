data "hcl_schema" "hit8" {
  paths = fileset("schemas/**/*.hcl")
}

env "dev" {
  src = data.hcl_schema.hit8.url
  url = "postgresql://postgres:postgres@localhost:54325/postgres?sslmode=disable&options=-c%20search_path%3Dhit8,extensions,public"
  schemas = ["hit8"] 
}

env "stg" {
  src = data.hcl_schema.hit8.url
  url = "${getenv("DIRECT_DB_CONNECTION_STRING")}&options=-c%20search_path%3Dhit8,extensions,public"
  schemas = ["hit8"] 
}

env "prd" {
  src = data.hcl_schema.hit8.url
  url = "${getenv("DIRECT_DB_CONNECTION_STRING")}&options=-c%20search_path%3Dhit8,extensions,public"
  schemas = ["hit8"] 
}
