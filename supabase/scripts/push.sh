#!/bin/bash
set -e

# Usage: 
#   Deploy:  doppler run -- ./supabase/scripts/push.sh
#   Try Out: doppler run -- ./supabase/scripts/push.sh --dry-run

# Move to project root
cd "$(dirname "$0")/../.."

# Parse arguments
DRY_RUN_FLAG=""
if [[ "$1" == "--dry-run" ]]; then
    echo "🔍 DRAGON RUN MODE: Simulating migration only..."
    DRY_RUN_FLAG="--dry-run"
else
    echo "🚀 Starting Deployment to Production..."
fi

# Validate Secret
if [ -z "$DIRECT_DB_CONNECTION_STRING" ]; then
    echo "❌ Error: DIRECT_DB_CONNECTION_STRING is not set."
    echo "   Example: doppler run -- ./supabase/scripts/push.sh --dry-run"
    exit 1
fi

# Run Push (with optional dry-run)
supabase db push --db-url "$DIRECT_DB_CONNECTION_STRING" $DRY_RUN_FLAG

if [[ "$1" == "--dry-run" ]]; then
    echo "✅ Simulation Complete. No changes were applied."
else
    echo "✅ Production Database is up to date."
fi
