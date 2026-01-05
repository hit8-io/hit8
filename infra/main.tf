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
