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
  
  API_RESPONSE=$(curl -sS -w "\n%{http_code}" -H "X-Auth-Token: ${SCALEWAY_SECRET_KEY}" \
    "https://api.scaleway.com/secret-manager/v1beta1/regions/${REGION}/secrets/${SECRET_UUID}/versions/latest/access")
  
  HTTP_CODE=$(echo "$API_RESPONSE" | tail -n1)
  API_BODY=$(echo "$API_RESPONSE" | sed '$d')
  
  if [ "$HTTP_CODE" != "200" ]; then
    echo "ERROR: Secret Manager API returned HTTP $HTTP_CODE"
    exit 1
  fi
  
  DOPPLER_TOKEN=$(echo "$API_BODY" | jq -r '.opaque_data // .data // empty' 2>/dev/null | tr -d '\n\r ')
  
  if [ -z "${DOPPLER_TOKEN}" ] || [ "${DOPPLER_TOKEN}" = "null" ]; then
    echo "ERROR: Failed to extract DOPPLER_TOKEN from Secret Manager"
    exit 1
  fi
  
  export DOPPLER_TOKEN
fi

if [ -n "${DOPPLER_TOKEN}" ]; then
  exec doppler run -- "$@"
else
  exec "$@"
fi
