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
      
      # Install Squid for HTTP/HTTPS traffic
      apt-get install -y squid
      sed -i "s/http_access allow localhost/http_access allow localhost\nacl allowed_networks src 10.0.0.0\/24 10.1.0.0\/24\nhttp_access allow allowed_networks/g" /etc/squid/squid.conf
      
      # Install Dante SOCKS5 proxy for TCP traffic (PostgreSQL, etc.)
      apt-get install -y dante-server
      
      # Configure Dante SOCKS5 proxy
      cat > /etc/danted.conf << 'DANTE_EOF'
      # Logging
      logoutput: /var/log/socks.log
      
      # Internal interface (VPC subnet)
      internal: 10.0.0.2 port = 1080
      
      # External interface (same as internal since no public IP)
      external: 10.0.0.2
      
      # Authentication method (none for internal VPC)
      socksmethod: none
      
      # Allow connections from VPC and peering networks
      client pass {
          from: 10.0.0.0/24 to: 0.0.0.0/0
          log: error connect disconnect
      }
      client pass {
          from: 10.1.0.0/24 to: 0.0.0.0/0
          log: error connect disconnect
      }
      
      # Allow outbound connections to any destination
      socks pass {
          from: 10.0.0.0/24 to: 0.0.0.0/0
          log: error connect disconnect
      }
      socks pass {
          from: 10.1.0.0/24 to: 0.0.0.0/0
          log: error connect disconnect
      }
      DANTE_EOF
      
      # Enable IP forwarding for routing
      echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
      sysctl -p
      
      # Configure iptables for NAT (since NAT gateway isn't working)
      iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
      iptables -A FORWARD -i eth0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT
      iptables -A FORWARD -i eth0 -o eth0 -j ACCEPT
      
      # Save iptables rules
      apt-get install -y iptables-persistent
      netfilter-persistent save || true
      
      # Start services
      systemctl enable squid danted
      systemctl restart squid danted
  EOT

  service_account {
    # Use the default compute SA or the specific one you listed
    email  = "617962194338-compute@developer.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }
}
