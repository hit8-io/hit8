#!/bin/bash

# --- Configuration ---
ACCOUNT_ID="b3264445f09fa6a420e40e424c81e23d"

# Ensure token is set
if [ -z "$CLOUDFARE_TOKEN" ]; then
    echo "Error: CLOUDFARE_TOKEN environment variable is not set."
    exit 1
fi

export CLOUDFLARE_API_TOKEN="$CLOUDFARE_TOKEN"

echo "--------------------------------------------------------"
echo "🔍 Auto-detecting Zone ID for 'hit8'..."
# Fetch Zone ID (needed for zone-level resources like DNS)
ZONE_ID_RESPONSE=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones?name=hit8.io" \
     -H "Authorization: Bearer $CLOUDFARE_TOKEN" \
     -H "Content-Type: application/json")
ZONE_ID=$(echo "$ZONE_ID_RESPONSE" | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['result'][0]['id']) if data['result'] else print('')")

if [ -z "$ZONE_ID" ]; then
    echo "⚠️  Zone ID not found. Only Account-level resources will be scanned."
else
    echo "✅ Found Zone ID: $ZONE_ID"
fi

# Create Output Directory
OUTPUT_DIR="generated_cf_terraforming"
mkdir -p "$OUTPUT_DIR"
echo "📂 Outputting files to: $OUTPUT_DIR"

# --- Function to Import a Resource Type ---
import_resource() {
    TYPE=$1
    SCOPE=$2 # "zone" or "account"
    ID=$3    # The Zone ID or Account ID

    echo "   ... Scanning $TYPE ($SCOPE)"
    
    # 1. Generate Config (.tf)
    if [ "$SCOPE" == "zone" ]; then
        cf-terraforming generate --resource-type "$TYPE" --zone "$ID" > "$OUTPUT_DIR/${TYPE}.tf" 2>/dev/null
    else
        cf-terraforming generate --resource-type "$TYPE" --account "$ID" > "$OUTPUT_DIR/${TYPE}.tf" 2>/dev/null
    fi

    # Check if file is empty (no resources found)
    if [ ! -s "$OUTPUT_DIR/${TYPE}.tf" ]; then
        rm "$OUTPUT_DIR/${TYPE}.tf"
        return
    fi

    # 2. Generate Import Blocks (.tf import) - Modern Terraform 1.5+ style
    # We append these to a separate 'imports.tf' file
    if [ "$SCOPE" == "zone" ]; then
        cf-terraforming import --resource-type "$TYPE" --zone "$ID" --modern-import-block >> "$OUTPUT_DIR/imports.tf" 2>/dev/null
    else
        cf-terraforming import --resource-type "$TYPE" --account "$ID" --modern-import-block >> "$OUTPUT_DIR/imports.tf" 2>/dev/null
    fi
    
    echo "   ✅ Found resources for $TYPE"
}

# --- LIST OF RESOURCES TO SCAN ---
echo "--------------------------------------------------------"
echo "🚀 Starting Full Scan..."

# Clean previous imports
rm -f "$OUTPUT_DIR/imports.tf"

# 1. ACCOUNT Level Resources
echo "--- Account Level ---"
import_resource "cloudflare_account_member" "account" "$ACCOUNT_ID"
import_resource "cloudflare_workers_script" "account" "$ACCOUNT_ID"
import_resource "cloudflare_worker_route" "zone" "$ZONE_ID" # Route is zone-level often
import_resource "cloudflare_tunnel" "account" "$ACCOUNT_ID"

# 2. ZONE Level Resources (Only if we found a Zone ID)
if [ ! -z "$ZONE_ID" ]; then
    echo "--- Zone Level ---"
    import_resource "cloudflare_record" "zone" "$ZONE_ID"
    import_resource "cloudflare_zone_settings_override" "zone" "$ZONE_ID"
    import_resource "cloudflare_page_rule" "zone" "$ZONE_ID"
    import_resource "cloudflare_filter" "zone" "$ZONE_ID"
    import_resource "cloudflare_firewall_rule" "zone" "$ZONE_ID"
    import_resource "cloudflare_ruleset" "zone" "$ZONE_ID"
fi

# --- Manual Pages Section (Since tool doesn't support generating it yet) ---
echo "--------------------------------------------------------"
echo "📝 Generating Manual Config for Pages..."
cat <<EOF > "$OUTPUT_DIR/pages_manual.tf"
# Manual Pages Config (Tool support limited)
resource "cloudflare_pages_project" "hit8" {
  account_id        = "$ACCOUNT_ID"
  name              = "hit8"
  production_branch = "main"
}
EOF

# Add import block for Pages manually
cat <<EOF >> "$OUTPUT_DIR/imports.tf"
import {
  to = cloudflare_pages_project.hit8
  id = "$ACCOUNT_ID/hit8"
}
EOF
echo "   ✅ Added Manual Pages Config"

# --- Provider Setup ---
cat <<EOF > "$OUTPUT_DIR/provider.tf"
terraform {
  required_providers {
    cloudflare = {
      source = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}
provider "cloudflare" {
  api_token = "$CLOUDFARE_TOKEN"
}
EOF

echo "--------------------------------------------------------"
echo "🎉 Done! Navigate to '$OUTPUT_DIR' and run:"
echo "   1. terraform init"
echo "   2. terraform plan"
echo "   3. terraform apply"
