#!/bin/bash
# Development script that always uses Doppler to inject secrets
# Usage: ./dev.sh [docker-compose command]
# Examples:
#   ./dev.sh up -d          # Start services in background
#   ./dev.sh up             # Start services in foreground
#   ./dev.sh down           # Stop services
#   ./dev.sh logs api       # View API logs
#   ./dev.sh ps             # Show service status

doppler run -- docker-compose "$@"

