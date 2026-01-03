#!/bin/bash
set -e

# Usage: ./supabase/scripts/diff.sh [optional_name]

# Move to project root
cd "$(dirname "$0")/../.."

CHANGE_NAME=$1
if [ -z "$CHANGE_NAME" ]; then
    # Auto-generate timestamped name if none provided
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    CHANGE_NAME="auto_diff_${TIMESTAMP}"
fi

echo "🔍 Generating migration diff: $CHANGE_NAME"

# Generate diff from Local DB vs Migration History
supabase db diff -f "$CHANGE_NAME"

# Find the newly created file
if ls supabase/migrations/*.sql 1> /dev/null 2>&1; then
    NEW_FILE=$(ls -t supabase/migrations/*.sql | head -1)
    echo "✅ Created: $NEW_FILE"
    echo "👉 Action: Review this file, then 'git add' and 'git commit'."
else
    echo "ℹ️  No schema changes detected. No migration file created."
fi

