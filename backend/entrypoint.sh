#!/bin/sh
# Run the app with Doppler when we have a token. Token can be:
# - DOPPLER_TOKEN set directly (e.g. GCP Secret Manager, or local doppler run)
# - DOPPLER_TOKEN_SECRET_ID set: fetch token from Scaleway Secret Manager API, then run doppler
set -e

# SCALEWAY_SECRET_KEY: Scaleway API secret key (SCW_SECRET_KEY is reserved by the platform)
if [ -z "${DOPPLER_TOKEN}" ] && [ -n "${DOPPLER_TOKEN_SECRET_ID}" ] && [ -n "${SCALEWAY_SECRET_KEY}" ]; then
  REGION="${SCALEWAY_SECRET_REGION:-fr-par}"
  
  # Extract UUID from secret ID (Terraform returns format: "fr-par/uuid" or just "uuid")
  SECRET_UUID="${DOPPLER_TOKEN_SECRET_ID##*/}"
  
  echo "Fetching DOPPLER_TOKEN from Scaleway Secret Manager (secret_id=${SECRET_UUID}, region=${REGION})..."
  
  API_RESPONSE=$(curl -sS -w "\n%{http_code}" -H "X-Auth-Token: ${SCALEWAY_SECRET_KEY}" \
    "https://api.scaleway.com/secret-manager/v1beta1/regions/${REGION}/secrets/${SECRET_UUID}/versions/latest/access")
  
  HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
  API_BODY=$(echo "$API_RESPONSE" | sed '$d')
  
  if [ "$HTTP_CODE" != "200" ]; then
    echo "ERROR: Failed to fetch DOPPLER_TOKEN from Secret Manager API (HTTP $HTTP_CODE)"
    echo "Response: $API_BODY"
    echo "Secret ID (full): ${DOPPLER_TOKEN_SECRET_ID}"
    echo "Secret UUID: ${SECRET_UUID}"
    echo "Region: ${REGION}"
    echo "API URL: https://api.scaleway.com/secret-manager/v1beta1/regions/${REGION}/secrets/${SECRET_UUID}/versions/latest/access"
    echo "Hint: Ensure the secret exists and has at least one version with a value"
    exit 1
  fi
  
  DOPPLER_TOKEN=$(echo "$API_BODY" | jq -r '.data // .opaque_data // . // empty')
  if [ -z "${DOPPLER_TOKEN}" ] || [ "${DOPPLER_TOKEN}" = "null" ]; then
    echo "ERROR: DOPPLER_TOKEN is empty after fetching from Secret Manager"
    echo "API Response: $API_BODY"
    echo "Secret UUID: ${SECRET_UUID}"
    echo "Hint: The secret exists but has no value. Add a version with: scw secret secret add-version ${SECRET_UUID} data=<token>"
    exit 1
  fi
  
  echo "Successfully fetched DOPPLER_TOKEN from Secret Manager"
  export DOPPLER_TOKEN
fi

if [ -n "${DOPPLER_TOKEN}" ]; then
  exec doppler run -- "$@"
else
  exec "$@"
fi
