#!/bin/sh
# Run the app with Doppler when we have a token. Token can be:
# - DOPPLER_TOKEN set directly (e.g. GCP Secret Manager, or local doppler run)
# - DOPPLER_TOKEN_SECRET_ID set: fetch token from Scaleway Secret Manager API, then run doppler
set -e

# SCALEWAY_SECRET_KEY: Scaleway API secret key (SCW_SECRET_KEY is reserved by the platform)
if [ -z "${DOPPLER_TOKEN}" ] && [ -n "${DOPPLER_TOKEN_SECRET_ID}" ] && [ -n "${SCALEWAY_SECRET_KEY}" ]; then
  REGION="${SCALEWAY_SECRET_REGION:-fr-par}"
  DOPPLER_TOKEN=$(curl -sS -H "X-Auth-Token: ${SCALEWAY_SECRET_KEY}" \
    "https://api.scaleway.com/secret-manager/v1beta1/regions/${REGION}/secrets/${DOPPLER_TOKEN_SECRET_ID}/versions/latest/access" \
    | jq -r '.data // .opaque_data // . // empty')
  if [ -z "${DOPPLER_TOKEN}" ]; then
    echo "Failed to fetch DOPPLER_TOKEN from Secret Manager (secret_id=${DOPPLER_TOKEN_SECRET_ID})"
    exit 1
  fi
  export DOPPLER_TOKEN
fi

if [ -n "${DOPPLER_TOKEN}" ]; then
  exec doppler run -- "$@"
else
  exec "$@"
fi
