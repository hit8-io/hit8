# ==============================================================================
# 1. SHARED INFRA (Registry)
# ==============================================================================

resource "scaleway_registry_namespace" "main" {
  name        = "hit8-registry"
  description = "Main Registry"
  project_id  = var.SCW_PROJECT_ID
  region      = var.SCW_REGION
  is_public   = false
}

locals {
  registry_endpoint = scaleway_registry_namespace.main.endpoint
}

# ==============================================================================
# 2. NETWORKING (VPC)
# ==============================================================================

resource "scaleway_vpc_private_network" "stg" {
  name       = "hit8-vpc-stg"
  project_id = var.SCW_PROJECT_ID
  region     = var.SCW_REGION
  tags       = ["hit8", "stg"]
}

resource "scaleway_vpc_private_network" "prd" {
  name       = "hit8-vpc-prd"
  project_id = var.SCW_PROJECT_ID
  region     = var.SCW_REGION
  tags       = ["hit8", "prd"]
}

# ==============================================================================
# 3. STAGING ENVIRONMENT (All-in-One VM: Docker Compose)
# ==============================================================================

resource "scaleway_instance_ip" "stg_vm_ipv6" {
  zone       = var.SCW_ZONE
  project_id = var.SCW_PROJECT_ID
  type       = "routed_ipv6"
}

resource "scaleway_instance_security_group" "stg_vm" {
  name       = "hit8-stg-sg"
  project_id = var.SCW_PROJECT_ID

  inbound_rule {
    action   = "accept"
    port     = 22
    ip_range = "::/0"
  }

  # Allow internal traffic (Postgres/Redis) from VPC only
  inbound_rule {
    action     = "accept"
    protocol   = "TCP"
    port_range = "5432-6432" # 5432=Postgres, 6432=PgBouncer
    ip_range   = "10.0.0.0/8"
  }
}

resource "scaleway_instance_server" "stg_vm" {
  name              = "hit8-stg-vm"
  type              = "DEV1-S"
  image             = "ubuntu_jammy"
  project_id        = var.SCW_PROJECT_ID
  zone              = var.SCW_ZONE
  ip_id             = scaleway_instance_ip.stg_vm_ipv6.id

  security_group_id = scaleway_instance_security_group.stg_vm.id

  private_network {
    pn_id = scaleway_vpc_private_network.stg.id
  }

  user_data = {
    cloud-init = <<-EOF
      #cloud-config
      package_update: true
      packages:
        - docker.io
        - docker-compose
        - fail2ban
      write_files:
        - path: /etc/ssh/sshd_config.d/99-hardening.conf
          content: |
            PermitRootLogin prohibit-password
            PasswordAuthentication no
            ChallengeResponseAuthentication no
            MaxAuthTries 3
            MaxSessions 5
            ClientAliveInterval 300
            ClientAliveCountMax 2
        - path: /etc/fail2ban/jail.local
          content: |
            [sshd]
            enabled = true
            maxretry = 3
            findtime = 600
            bantime = 3600
        - path: /root/docker-compose.yml
          content: |
            services:
              postgres:
                image: postgres:17-alpine
                restart: always
                environment:
                  POSTGRES_USER: hit8
                  POSTGRES_PASSWORD: hit8
                  POSTGRES_DB: hit8
                volumes:
                  - pgdata:/var/lib/postgresql/data
              redis:
                image: redis:7-alpine
                restart: always
                command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
              pgbouncer:
                image: edoburu/pgbouncer:latest
                restart: always
                environment:
                  DATABASE_URL: "postgres://hit8:hit8@postgres:5432/hit8"
                  POOL_MODE: transaction
                  MAX_CLIENT_CONN: 100
                  AUTH_TYPE: trust
                ports:
                  - "6432:6432"
                depends_on:
                  - postgres
            volumes:
              pgdata:
      runcmd:
        - systemctl restart sshd
        - systemctl enable fail2ban
        - systemctl start fail2ban
        - cd /root && docker-compose up -d
    EOF
  }
}

# ==============================================================================
# 4. PRODUCTION ENVIRONMENT (Managed DB + DEV1-S Redis)
# ==============================================================================

# Data sources to get private NIC IPv4/IPv6 addresses
data "scaleway_instance_private_nic" "prd_redis" {
  server_id          = scaleway_instance_server.prd_redis.id
  private_network_id = scaleway_vpc_private_network.prd.id
  zone               = scaleway_instance_server.prd_redis.zone

  depends_on = [scaleway_instance_server.prd_redis]
}

data "scaleway_instance_private_nic" "stg_vm" {
  server_id          = scaleway_instance_server.stg_vm.id
  private_network_id = scaleway_vpc_private_network.stg.id
  zone               = scaleway_instance_server.stg_vm.zone

  depends_on = [scaleway_instance_server.stg_vm]
}

locals {
  # Prefer IPv4 (contains a dot), else fall back to first address
  prd_redis_private_ip = try(
    [for ip in data.scaleway_instance_private_nic.prd_redis.private_ips : ip.address if can(regex("\\.", ip.address))][0],
    [for ip in data.scaleway_instance_private_nic.prd_redis.private_ips : ip.address][0],
  )

  stg_vm_private_ip = try(
    [for ip in data.scaleway_instance_private_nic.stg_vm.private_ips : ip.address if can(regex("\\.", ip.address))][0],
    [for ip in data.scaleway_instance_private_nic.stg_vm.private_ips : ip.address][0],
  )
}

# 4a. Managed Postgres (public IPv4 endpoint is created by default; see prd_rdb_public_endpoint output)
resource "scaleway_rdb_instance" "prd_db" {
  name           = "hit8-db-prd"
  node_type      = "DB-DEV-S"
  engine         = "PostgreSQL-17"
  is_ha_cluster  = false
  disable_backup = false
  project_id     = var.SCW_PROJECT_ID
  region         = var.SCW_REGION

  user_name = "hit8"
  password  = var.SCW_PRD_DB_PWD

  volume_type       = "sbs_5k"
  volume_size_in_gb = 10

  private_network {
    pn_id       = scaleway_vpc_private_network.prd.id
    enable_ipam = true
  }

  lifecycle {
    prevent_destroy = true

    postcondition {
      condition     = self.disable_backup == false
      error_message = "Production database backups must be enabled (disable_backup = false)."
    }
  }
}

resource "scaleway_instance_ip" "prd_redis_ipv6" {
  zone       = var.SCW_ZONE
  project_id = var.SCW_PROJECT_ID
  type       = "routed_ipv6"
}

# 4b. Redis on DEV1-S
resource "scaleway_instance_security_group" "prd_redis_sg" {
  name       = "hit8-prd-redis-sg"
  project_id = var.SCW_PROJECT_ID

  inbound_rule {
    action   = "accept"
    port     = 6379
    ip_range = "10.0.0.0/8"
  }
  inbound_rule {
    action   = "accept"
    port     = 22
    ip_range = "::/0"
  }
}

resource "scaleway_instance_server" "prd_redis" {
  name              = "hit8-prd-redis"
  type              = "DEV1-S"
  image             = "ubuntu_jammy"
  project_id        = var.SCW_PROJECT_ID
  zone              = var.SCW_ZONE
  ip_id             = scaleway_instance_ip.prd_redis_ipv6.id

  security_group_id = scaleway_instance_security_group.prd_redis_sg.id

  private_network {
    pn_id = scaleway_vpc_private_network.prd.id
  }

  user_data = {
    cloud-init = <<-EOF
      #cloud-config
      package_update: true
      packages:
        - redis-server
        - fail2ban
      write_files:
        - path: /etc/ssh/sshd_config.d/99-hardening.conf
          content: |
            PermitRootLogin prohibit-password
            PasswordAuthentication no
            ChallengeResponseAuthentication no
            MaxAuthTries 3
            MaxSessions 5
            ClientAliveInterval 300
            ClientAliveCountMax 2
        - path: /etc/fail2ban/jail.local
          content: |
            [sshd]
            enabled = true
            maxretry = 3
            findtime = 600
            bantime = 3600
      runcmd:
        - sed -i 's/^bind 127.0.0.1 ::1/bind 0.0.0.0 ::1/' /etc/redis/redis.conf
        - echo "maxmemory 512mb" >> /etc/redis/redis.conf
        - echo "maxmemory-policy allkeys-lru" >> /etc/redis/redis.conf
        - systemctl restart sshd
        - systemctl enable fail2ban
        - systemctl start fail2ban
        - systemctl restart redis-server
    EOF
  }

  lifecycle {
    prevent_destroy = true
  }
}

# ==============================================================================
# 4b. SECRET MANAGER (Doppler token for containers)
# ==============================================================================
# Same pattern as GCP: store only the Doppler service token in Secret Manager.
# No secret value in Terraform. Populate via Console or CLI after apply:
#   scw secret secret version create <secret-id> data="$(echo -n 'dp.st.xxx' | base64)" region=fr-par
# Containers fetch the token at startup via the Secret Manager API (using
# SCW credentials); see backend/entrypoint.sh and
# https://www.scaleway.com/en/developers/api/secret-manager/#path-secrets-allow-a-product-to-use-the-secret

resource "scaleway_secret" "doppler_token_prd" {
  name        = "doppler-token-prd"
  description = "Doppler service token for hit8-api-prd (doppler run)"
  project_id  = var.SCW_PROJECT_ID
  region      = var.SCW_REGION
}

resource "scaleway_secret" "doppler_token_stg" {
  name        = "doppler-token-stg"
  description = "Doppler service token for hit8-api-stg (doppler run)"
  project_id  = var.SCW_PROJECT_ID
  region      = var.SCW_REGION
}

# ==============================================================================
# 5. COMPUTE (Serverless Containers - API)
# ==============================================================================

resource "scaleway_container_namespace" "api" {
  name        = "hit8-api-ns"
  description = "Namespace for Hit8 API containers"
  project_id  = var.SCW_PROJECT_ID
  region      = var.SCW_REGION

  environment_variables = {
    "TZ" = "Europe/Brussels"
  }
}

# PRD Container — attached to prd VPC so it can reach RDB and Redis via private IPs
resource "scaleway_container" "api_prd" {
  name               = "hit8-api-prd"
  namespace_id       = scaleway_container_namespace.api.id
  registry_image     = "${local.registry_endpoint}/api:${var.CONTAINER_IMAGE}"
  private_network_id = scaleway_vpc_private_network.prd.id

  cpu_limit    = 1000
  memory_limit = 2048
  min_scale    = 1
  max_scale    = 5
  port         = 8080

  environment_variables = {
    "ENVIRONMENT"               = "prd"
    "DOPPLER_PROJECT"           = var.DOPPLER_PROJECT
    "DOPPLER_CONFIG"            = "prd"
    "DOPPLER_TOKEN_SECRET_ID"   = scaleway_secret.doppler_token_prd.id
    "SCALEWAY_SECRET_REGION"    = var.SCW_REGION
    "DB_HOST"                   = scaleway_rdb_instance.prd_db.private_network[0].ip
    "REDIS_HOST"                = local.prd_redis_private_ip
  }

  # Container uses these to call Secret Manager API and fetch DOPPLER_TOKEN at startup.
  # SCW_SECRET_KEY is reserved by Scaleway; use SCALEWAY_SECRET_KEY instead.
  secret_environment_variables = {
    "SCALEWAY_SECRET_KEY" = var.SCW_SECRET_KEY
  }
}

# STG Container — attached to stg VPC so it can reach Postgres/Redis on stg VM via private IP
resource "scaleway_container" "api_stg" {
  name               = "hit8-api-stg"
  namespace_id       = scaleway_container_namespace.api.id
  registry_image     = "${local.registry_endpoint}/api:${var.CONTAINER_IMAGE}"
  private_network_id = scaleway_vpc_private_network.stg.id

  cpu_limit    = 500
  memory_limit = 1024
  min_scale    = 0
  max_scale    = 2
  port         = 8080

  environment_variables = {
    "ENVIRONMENT"               = "stg"
    "DOPPLER_PROJECT"           = var.DOPPLER_PROJECT
    "DOPPLER_CONFIG"            = "stg"
    "DOPPLER_TOKEN_SECRET_ID"   = scaleway_secret.doppler_token_stg.id
    "SCALEWAY_SECRET_REGION"    = var.SCW_REGION
    "DB_HOST"                   = local.stg_vm_private_ip
    "DB_PORT"                   = "6432"
    "REDIS_HOST"                = local.stg_vm_private_ip
  }

  secret_environment_variables = {
    "SCALEWAY_SECRET_KEY" = var.SCW_SECRET_KEY
  }
}

# ==============================================================================
# 6. DOMAINS (Ingress)
# ==============================================================================

resource "scaleway_container_domain" "prd" {
  container_id = scaleway_container.api_prd.id
  hostname     = "scw-prd.hit8.io"
}

resource "scaleway_container_domain" "stg" {
  container_id = scaleway_container.api_stg.id
  hostname     = "scw-stg.hit8.io"
}

# ==============================================================================
# 7. OUTPUTS
# ==============================================================================

output "registry_login" {
  value = "docker login ${local.registry_endpoint}"
}

output "stg_vm_ipv6" {
  value       = scaleway_instance_ip.stg_vm_ipv6.address
  description = "Staging VM public IPv6 address"
}

output "prd_redis_ipv6" {
  value       = scaleway_instance_ip.prd_redis_ipv6.address
  description = "Production Redis VM public IPv6 address"
}

output "stg_ssh_command" {
  value = "ssh root@${scaleway_instance_ip.stg_vm_ipv6.address}"
}

# Public IPv4 endpoint (Scaleway creates the load balancer by default on RDB instances).
output "prd_rdb_public_endpoint" {
  value = length(scaleway_rdb_instance.prd_db.load_balancer) > 0 ? {
    ip       = scaleway_rdb_instance.prd_db.load_balancer[0].ip
    port     = scaleway_rdb_instance.prd_db.load_balancer[0].port
    hostname = scaleway_rdb_instance.prd_db.load_balancer[0].hostname
  } : null
  description = "Production RDB public IPv4 endpoint (load balancer). Re-add in console if removed."
}

output "connection_info" {
  value = {
    prd_db_ip     = scaleway_rdb_instance.prd_db.private_network[0].ip
    prd_db_public = length(scaleway_rdb_instance.prd_db.load_balancer) > 0 ? "${scaleway_rdb_instance.prd_db.load_balancer[0].ip}:${scaleway_rdb_instance.prd_db.load_balancer[0].port}" : null
    prd_redis_ip  = local.prd_redis_private_ip
    stg_vm_ip     = local.stg_vm_private_ip
    note          = "Containers are attached to VPC (api_prd → prd PN, api_stg → stg PN) and use private IPs for DB/Redis."
  }
}
