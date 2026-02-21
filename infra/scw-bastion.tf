# ==============================================================================
# 4c. ADMIN BASTION VM (STARDUST1-S in PAR1 for Postgres access)
# ==============================================================================

resource "scaleway_instance_ip" "prd_bastion_ipv6" {
  zone       = "fr-par-1"
  project_id = var.SCW_PROJECT_ID
  type       = "routed_ipv6"
}

resource "scaleway_instance_security_group" "prd_bastion_sg" {
  zone       = "fr-par-1"
  name       = "hit8-prd-bastion-sg"
  project_id = var.SCW_PROJECT_ID

  inbound_rule {
    action   = "accept"
    port     = 22
    ip_range = "::/0"
  }

  inbound_rule {
    action   = "accept"
    protocol = "ICMP"
    ip_range = "::/0"
  }

  # Allow Postgres access from VPC only
  inbound_rule {
    action   = "accept"
    protocol = "TCP"
    port     = 5432
    ip_range = "10.0.0.0/8"
  }
}

resource "scaleway_instance_server" "prd_bastion" {
  name              = "hit8-prd-bastion"
  type              = "STARDUST1-S"
  image             = "ubuntu_jammy"
  project_id        = var.SCW_PROJECT_ID
  zone              = "fr-par-1"
  ip_id             = scaleway_instance_ip.prd_bastion_ipv6.id
  security_group_id = scaleway_instance_security_group.prd_bastion_sg.id

  private_network {
    pn_id = scaleway_vpc_private_network.prd.id
  }

  root_volume {
    size_in_gb = 10
  }

  user_data = {
    cloud-init = <<-EOF
      #cloud-config
      package_update: true
      packages:
        - postgresql-client
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
        - systemctl restart sshd
        - systemctl enable fail2ban
        - systemctl start fail2ban
    EOF
  }

  lifecycle {
    prevent_destroy = true
  }
}

# Data source to get bastion private IP for outputs
data "scaleway_instance_private_nic" "prd_bastion" {
  server_id          = scaleway_instance_server.prd_bastion.id
  private_network_id = scaleway_vpc_private_network.prd.id
  zone               = scaleway_instance_server.prd_bastion.zone

  depends_on = [scaleway_instance_server.prd_bastion]
}

locals {
  prd_bastion_private_ip = try(
    [for ip in data.scaleway_instance_private_nic.prd_bastion.private_ips : ip.address if can(regex("\\.", ip.address))][0],
    [for ip in data.scaleway_instance_private_nic.prd_bastion.private_ips : ip.address][0],
  )
}
