provider "google" {
  project = "hit8-poc"
  region  = "europe-west1"
  zone    = "europe-west1-b"
}

data "google_compute_image" "proxy_image" {
  family  = "proxy-gateway"
  project = "hit8-poc"
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
      # Point to the specific SELF_LINK of the data source
      image = data.google_compute_image.proxy_image.self_link
      size  = 20
    }
  }
  
  network_interface {
    network    = google_compute_network.vpc.name
    subnetwork = google_compute_subnetwork.subnet.name
    network_ip = "10.0.0.2"
  }

  service_account {
    # Use the default compute SA or the specific one you listed
    email  = "617962194338-compute@developer.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }
}
