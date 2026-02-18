#!/bin/bash

# Configuratie
ZONE="fr-par-1"    
IMAGE="ubuntu_jammy"
NAME="hit8-stg-postgres"
PROJECT_ID="46cd93dd-07f0-4c76-bc82-9634149aaca3"

echo "Starting Stardust Hunt in $ZONE..."

while true; do
  # Probeer instance aan te maken
  OUTPUT=$(scw instance server create type=STARDUST1-S zone=$ZONE image=$IMAGE name=$NAME project-id=$PROJECT_ID ip=ipv6 root-volume=local:10GB 2>&1)
  
  if [[ $? -eq 0 ]]; then
    echo "SUCCESS! Stardust instance created!"
    echo "$OUTPUT"
    # Stop de loop
    break
  else
    # Check of het een 'out of stock' error is
    if [[ "$OUTPUT" == *"Insufficient capacity"* ]] || [[ "$OUTPUT" == *"out of stock"* ]]; then
      echo "[$(date +%T)] Out of stock. Retrying in 60 seconds..."
      sleep 60
    else
      # Andere error? Stop script
      echo "ERROR: Something else went wrong:"
      echo "$OUTPUT"
      exit 1
    fi
  fi
done
