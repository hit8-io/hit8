#!/bin/bash
# check-and-import.sh
# Script to check existing GCP resources and generate import commands
# Only imports resources that exist - does not create new ones

set -e

PROJECT_ID="${PROJECT_ID:-hit8-poc}"
INFRA_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Checking Existing GCP Resources ==="
echo "Project: $PROJECT_ID"
echo ""

# Check if gcloud is available and working
if ! command -v gcloud &> /dev/null; then
  echo "❌ Error: gcloud CLI is not installed or not in PATH"
  exit 1
fi

# Test gcloud authentication and access
if ! gcloud projects describe "$PROJECT_ID" &>/dev/null; then
  echo "❌ Error: Cannot access project '$PROJECT_ID'"
  echo "   Please authenticate: gcloud auth login"
  echo "   And set project: gcloud config set project $PROJECT_ID"
  exit 1
fi

cd "$INFRA_DIR"

# Check if terraform is initialized
if [ ! -d "$INFRA_DIR/.terraform" ]; then
  echo "⚠️  Terraform not initialized. Running 'terraform init'..."
  terraform init
fi

# Get Terraform state (if it exists)
TERRAFORM_RESOURCES=""
if terraform state list >/dev/null 2>&1; then
  TERRAFORM_RESOURCES=$(terraform state list)
fi

echo "=== Artifact Registry Repositories ==="
# Use CSV format which is more reliable and easier to parse
REPOS_OUTPUT=$(gcloud artifacts repositories list --project=$PROJECT_ID --format="csv(name,location)" --filter="name:*" 2>&1)
REPOS_EXIT_CODE=$?

if [ $REPOS_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Error listing Artifact Registry repositories:"
  echo "$REPOS_OUTPUT" | head -3
  echo ""
else
  # Skip header line and process each repository
  echo "$REPOS_OUTPUT" | tail -n +2 | while IFS=',' read -r repo_full location_raw || [ -n "$repo_full" ]; do
    # Skip empty lines
    [ -z "$repo_full" ] && continue
    
    # Clean up the values (remove quotes if present, trim whitespace)
    repo_full=$(echo "$repo_full" | sed 's/^"//;s/"$//;s/^ *//;s/ *$//')
    location=$(echo "$location_raw" | sed 's/^"//;s/"$//;s/^ *//;s/ *$//' 2>/dev/null || echo "")
    
    # Extract repository name from full path
    REPO_NAME=$(echo "$repo_full" | sed -n 's|.*/repositories/\([^/]*\)$|\1|p')
    
    # If location wasn't in CSV, extract from name path
    if [ -z "$location" ]; then
      location=$(echo "$repo_full" | sed -n 's|.*/locations/\([^/]*\)/repositories/.*|\1|p')
    fi
    
    # Skip if we can't extract required info
    if [ -z "$REPO_NAME" ] || [ -z "$location" ]; then
      continue
    fi
    
    if echo "$TERRAFORM_RESOURCES" | grep -q "google_artifact_registry_repository.backend_api"; then
      echo "✅ Repository '$REPO_NAME' (location: $location) already in Terraform state"
    else
      echo "📦 Repository '$REPO_NAME' (location: $location) exists but NOT in Terraform"
      echo "   Import command:"
      echo "   terraform import google_artifact_registry_repository.backend_api \\"
      echo "     projects/$PROJECT_ID/locations/$location/repositories/$REPO_NAME"
      echo ""
    fi
  done
  
  # Check if we found any repositories
  REPO_COUNT=$(echo "$REPOS_OUTPUT" | tail -n +2 | grep -c . || echo "0")
  if [ "$REPO_COUNT" -eq 0 ]; then
    echo "ℹ️  No Artifact Registry repositories found"
  fi
fi

echo ""
echo "=== Secret Manager Secrets ==="
SECRETS_OUTPUT=$(gcloud secrets list --project=$PROJECT_ID --format="value(name)" 2>&1)
SECRETS_EXIT_CODE=$?

if [ $SECRETS_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Error listing secrets:"
  echo "$SECRETS_OUTPUT" | head -3
  echo ""
else
  SECRETS="$SECRETS_OUTPUT"
  
  if [ -n "$SECRETS" ]; then
  for secret in $SECRETS; do
    if echo "$TERRAFORM_RESOURCES" | grep -q "google_secret_manager_secret.doppler_secrets"; then
      echo "✅ Secret '$secret' already in Terraform state"
    else
      echo "🔐 Secret '$secret' exists but NOT in Terraform"
      echo "   Import command:"
      echo "   terraform import google_secret_manager_secret.doppler_secrets \\"
      echo "     projects/$PROJECT_ID/secrets/$secret"
      echo ""
    fi
  done
  else
    echo "ℹ️  No secrets found"
  fi
fi

echo ""
echo "=== Cloud Run Services ==="
SERVICES_OUTPUT=$(gcloud run services list --project=$PROJECT_ID --format="value(name,region)" 2>&1)
SERVICES_EXIT_CODE=$?

if [ $SERVICES_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Error listing Cloud Run services:"
  echo "$SERVICES_OUTPUT" | head -3
  echo ""
else
  SERVICES="$SERVICES_OUTPUT"
  
  if [ -n "$SERVICES" ]; then
  echo "$SERVICES" | while IFS=$'\t' read -r SERVICE_NAME SERVICE_REGION; do
    # Fallback to default region if not found
    if [ -z "$SERVICE_REGION" ]; then
      SERVICE_REGION="europe-west1"
    fi
    
        if echo "$TERRAFORM_RESOURCES" | grep -q "google_cloud_run_service.api"; then
          echo "✅ Cloud Run service '$SERVICE_NAME' already in Terraform state"
        else
          echo "🚀 Cloud Run service '$SERVICE_NAME' exists but NOT in Terraform"
          echo "   Import command:"
          echo "   terraform import google_cloud_run_service.api \\"
          echo "     $SERVICE_REGION/$PROJECT_ID/$SERVICE_NAME"
          echo ""
        fi
  done
  else
    echo "ℹ️  No Cloud Run services found"
  fi
fi

echo ""
echo "=== Service Accounts ==="
SA_OUTPUT=$(gcloud iam service-accounts list --project=$PROJECT_ID --format="value(email)" 2>&1)
SA_EXIT_CODE=$?

if [ $SA_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Error listing service accounts:"
  echo "$SA_OUTPUT" | head -3
  echo ""
else
  SERVICE_ACCOUNTS="$SA_OUTPUT"
  
  if [ -n "$SERVICE_ACCOUNTS" ]; then
  for sa_email in $SERVICE_ACCOUNTS; do
    SA_NAME=$(echo "$sa_email" | cut -d'@' -f1)
    
    if echo "$TERRAFORM_RESOURCES" | grep -q "google_service_account.cloud_run_sa"; then
      echo "✅ Service account '$SA_NAME' already in Terraform state"
    elif [ "$SA_NAME" = "cloud-run-api" ]; then
      echo "👤 Service account '$SA_NAME' exists but NOT in Terraform"
      echo "   Import command:"
      echo "   terraform import google_service_account.cloud_run_sa \\"
      echo "     projects/$PROJECT_ID/serviceAccounts/$sa_email"
      echo ""
    fi
  done
  else
    echo "ℹ️  No service accounts found"
  fi
fi

echo ""
echo "=== Compute Networks ==="
NETWORKS_OUTPUT=$(gcloud compute networks list --project=$PROJECT_ID --format="value(name)" 2>&1)
NETWORKS_EXIT_CODE=$?

if [ $NETWORKS_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Error listing networks:"
  echo "$NETWORKS_OUTPUT" | head -3
  echo ""
else
  NETWORKS="$NETWORKS_OUTPUT"
  
  if [ -n "$NETWORKS" ]; then
  for network in $NETWORKS; do
    # Check if this specific network is in Terraform state
    IN_STATE=false
    if [ "$network" = "production-vpc" ]; then
      if echo "$TERRAFORM_RESOURCES" | grep -q "google_compute_network.vpc"; then
        IN_STATE=true
      fi
    fi
    
    # For default network, check if it's explicitly in state (it shouldn't be)
    if echo "$network" | grep -qi "default"; then
      if echo "$TERRAFORM_RESOURCES" | grep -qi "default"; then
        IN_STATE=true
      fi
    fi
    
    if [ "$IN_STATE" = true ]; then
      echo "✅ Network '$network' already in Terraform state"
      if echo "$network" | grep -qi "default"; then
        echo "   ⚠️  Note: Default network should NOT be managed by Terraform"
        echo "   To remove: terraform state rm <resource_name>"
      fi
      echo ""
    elif [ "$network" = "production-vpc" ]; then
      echo "🌐 Network '$network' exists but NOT in Terraform"
      echo "   Import command:"
      echo "   terraform import google_compute_network.vpc \\"
      echo "     projects/$PROJECT_ID/global/networks/$network"
      echo ""
    else
      # Default network - don't show import commands, just note it exists
      echo "ℹ️  Network '$network' exists but NOT in Terraform (as expected for default network)"
    fi
  done
  else
    echo "ℹ️  No networks found"
  fi
fi

echo ""
echo "=== Compute Subnets ==="
SUBNETS_OUTPUT=$(gcloud compute networks subnets list --project=$PROJECT_ID --format="value(name,region)" 2>&1)
SUBNETS_EXIT_CODE=$?

if [ $SUBNETS_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Error listing subnets:"
  echo "$SUBNETS_OUTPUT" | head -3
  echo ""
else
  SUBNETS="$SUBNETS_OUTPUT"
  
  if [ -n "$SUBNETS" ]; then
  echo "$SUBNETS" | while read -r subnet_info; do
    SUBNET_NAME=$(echo "$subnet_info" | cut -d' ' -f1)
    SUBNET_REGION=$(echo "$subnet_info" | cut -d' ' -f2)
    
    # Skip if name or region is empty
    [ -z "$SUBNET_NAME" ] && continue
    [ -z "$SUBNET_REGION" ] && continue
    
    # Check if this specific subnet is in Terraform state
    # Look for the subnet by constructing the expected resource name
    # Default subnets are usually not in state, production-subnet might be
    IN_STATE=false
    if [ "$SUBNET_NAME" = "production-subnet" ]; then
      if echo "$TERRAFORM_RESOURCES" | grep -q "google_compute_subnetwork.subnet"; then
        IN_STATE=true
      fi
    fi
    
    # For default subnets, check if they're explicitly in state (they shouldn't be)
    if echo "$SUBNET_NAME" | grep -qi "default"; then
      # Check if there's a default subnet resource in state (there shouldn't be)
      if echo "$TERRAFORM_RESOURCES" | grep -qi "default"; then
        IN_STATE=true
      fi
    fi
    
    if [ "$IN_STATE" = true ]; then
      echo "✅ Subnet '$SUBNET_NAME' (region: $SUBNET_REGION) already in Terraform state"
      echo "   ⚠️  Note: Default subnets should NOT be managed by Terraform"
      echo "   To remove: terraform state rm <resource_name>"
      echo ""
    elif [ "$SUBNET_NAME" = "production-subnet" ]; then
      echo "🔗 Subnet '$SUBNET_NAME' (region: $SUBNET_REGION) exists but NOT in Terraform"
      echo "   Import command:"
      echo "   terraform import google_compute_subnetwork.subnet \\"
      echo "     projects/$PROJECT_ID/regions/$SUBNET_REGION/subnetworks/$SUBNET_NAME"
      echo ""
    else
      # Default subnets - don't show import commands, just note they exist
      echo "ℹ️  Subnet '$SUBNET_NAME' (region: $SUBNET_REGION) exists but NOT in Terraform (as expected)"
    fi
  done
  else
    echo "ℹ️  No subnets found"
  fi
fi

echo ""
echo "=== Static IP Addresses ==="
ADDRESSES_OUTPUT=$(gcloud compute addresses list --project=$PROJECT_ID --format="value(name,region)" 2>&1)
ADDRESSES_EXIT_CODE=$?

if [ $ADDRESSES_EXIT_CODE -ne 0 ]; then
  echo "⚠️  Error listing static IP addresses:"
  echo "$ADDRESSES_OUTPUT" | head -3
  echo ""
else
  ADDRESSES="$ADDRESSES_OUTPUT"
  
  if [ -n "$ADDRESSES" ]; then
  echo "$ADDRESSES" | while read -r addr_info; do
    ADDR_NAME=$(echo "$addr_info" | cut -d' ' -f1)
    ADDR_REGION=$(echo "$addr_info" | cut -d' ' -f2)
    
    if echo "$TERRAFORM_RESOURCES" | grep -q "google_compute_address.egress_ip"; then
      echo "✅ Address '$ADDR_NAME' already in Terraform state"
    elif [ "$ADDR_NAME" = "production-static-egress-ip" ]; then
      echo "📍 Address '$ADDR_NAME' exists but NOT in Terraform"
      echo "   Import command:"
      echo "   terraform import google_compute_address.egress_ip \\"
      echo "     projects/$PROJECT_ID/regions/$ADDR_REGION/addresses/$ADDR_NAME"
      echo ""
    fi
  done
  else
    echo "ℹ️  No static IP addresses found"
  fi
fi

echo ""
echo "=== Summary ==="
echo "Run the import commands shown above to import existing resources into Terraform."
echo "Resources that don't exist will be skipped (Terraform won't create them if you only import)."
echo ""
echo "After importing, verify with:"
echo "  terraform plan"

