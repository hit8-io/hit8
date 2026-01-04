provider "google" {
  project = "hit8-poc"
  region  = "europe-west1"
  zone    = "europe-west1-b"
}

# 1. The Static IP (Crucial to import this first to save it)
resource "google_compute_address" "egress_ip" {
  name   = "production-static-egress-ip"
  region = "europe-west1"
}

# 2. VPC and Subnet
resource "google_compute_network" "vpc" {
  name                    = "production-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "subnet" {
  name          = "production-subnet"
  ip_cidr_range = "10.0.0.0/24"
  region        = "europe-west1"
  network       = google_compute_network.vpc.id
}

# 3. Cloud Router & NAT
resource "google_compute_router" "router" {
  name    = "production-router"             
  network = google_compute_network.vpc.id
  region  = "europe-west1"
}

resource "google_compute_router_nat" "nat" {
  name                               = "production-nat-gateway" 
  router                             = google_compute_router.router.name
  region                             = "europe-west1"
  nat_ip_allocate_option             = "MANUAL_ONLY"
  nat_ips                            = [google_compute_address.egress_ip.self_link]
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_PRIMARY_IP_RANGES"
}

# 4. Firewall Rules
resource "google_compute_firewall" "allow_proxy" {
  name    = "allow-proxy-access"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["3128", "1080"]  # Squid (HTTP) and Dante (SOCKS5)
  }

  source_ranges = ["10.0.0.0/8"] # Covers VPC and Peering
  target_tags   = ["proxy-server"]
}

# 5. The Proxy VM
resource "google_compute_instance" "proxy_vm" {
  name         = "build-proxy"
  machine_type = "e2-micro"
  zone         = "europe-west1-b"
  tags         = ["proxy-server"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
    }
  }

  network_interface {
    network    = google_compute_network.vpc.name
    subnetwork = google_compute_subnetwork.subnet.name
    network_ip = "10.0.0.2"
    # access_config {}
  }


  metadata_startup_script = <<-EOT
    #! /bin/bash
    apt-get update
    apt-get install -y squid dante-server iptables-persistent

    # --- SQUID CONFIGURATION ---
    # Backup original
    cp /etc/squid/squid.conf /etc/squid/squid.conf.bak

    # Create a simple, permissive config
    cat > /etc/squid/squid.conf << 'EOF'
    # Define local networks
    acl localnet src 10.0.0.0/8     # RFC1918 possible internal network
    acl localnet src 172.16.0.0/12  # RFC1918 possible internal network
    acl localnet src 192.168.0.0/16 # RFC1918 possible internal network

    # SSL Ports allowed
    acl SSL_ports port 443
    acl Safe_ports port 80          # http
    acl Safe_ports port 21          # ftp
    acl Safe_ports port 443         # https
    acl Safe_ports port 70          # gopher
    acl Safe_ports port 210         # wais
    acl Safe_ports port 1025-65535  # unregistered ports
    acl Safe_ports port 280         # http-mgmt
    acl Safe_ports port 488         # gss-http
    acl Safe_ports port 591         # filemaker
    acl Safe_ports port 777         # multiling http
    acl CONNECT method CONNECT

    # Access Rules
    http_access deny !Safe_ports
    http_access deny CONNECT !SSL_ports
    http_access allow localhost manager
    http_access deny manager

    # ALLOW LOCALNET (This is the key fix)
    http_access allow localnet
    http_access allow localhost

    # Deny everything else
    http_access deny all

    # Port
    http_port 3128
    EOF

    systemctl restart squid

    # --- DANTE CONFIGURATION (Keep your existing Dante config below) ---
    cat > /etc/danted.conf << 'DANTE_EOF'
    logoutput: /var/log/socks.log
    internal: 10.0.0.2 port = 1080
    external: 10.0.0.2
    socksmethod: none
    client pass { from: 10.0.0.0/8 to: 0.0.0.0/0 }
    socks pass { from: 10.0.0.0/8 to: 0.0.0.0/0 }
    DANTE_EOF

    systemctl restart danted
  EOT

  service_account {
    # Use the default compute SA or the specific one you listed
    email  = "617962194338-compute@developer.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }
}
