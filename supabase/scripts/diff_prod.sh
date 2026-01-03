#!/bin/bash
set -e

# Check for connection string
if [ -z "$DIRECT_DB_CONNECTION_STRING" ]; then
    echo "❌ Error: DIRECT_DB_CONNECTION_STRING is not set."
    echo "   Use: doppler run --config prd -- ./supabase/scripts/diff_prod.sh"
    exit 1
fi

# Configuration
LOCAL_DB_URL="postgres://postgres:postgres@localhost:5432/hit8"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="../migrations/${TIMESTAMP}_migration.sql"

mkdir -p "$(dirname "$OUTPUT_FILE")"

# Generate migration plan
echo "🔍 Comparing Production (current) with Schema files (desired)..."

export PATH="$HOME/go/bin:$PATH"
pg-schema-diff plan \
  --from-dsn "$DIRECT_DB_CONNECTION_STRING" \
  --to-dir "../schema" \
  --temp-db-dsn "$LOCAL_DB_URL" \
  --exclude-schema auth \
  --exclude-schema storage \
  --exclude-schema realtime \
  --exclude-schema vault \
  --exclude-schema extensions \
  --exclude-schema pg_graphql \
  --exclude-schema pg_stat_statements \
  --exclude-schema supabase_vault \
  --exclude-schema pgbouncer \
  --exclude-schema graphql \
  --disable-plan-validation \
  > "$OUTPUT_FILE"

# Safety filters - remove dangerous statements
echo "🛡️  Applying safety filters..."

if [[ "$OSTYPE" == "darwin"* ]]; then
    # Remove Supabase schema drops
    sed -i '' '/DROP SCHEMA IF EXISTS \(auth\|storage\|realtime\|vault\)/d' "$OUTPUT_FILE"
    # Remove extension changes (extensions managed separately)
    sed -i '' '/CREATE EXTENSION/d' "$OUTPUT_FILE"
    sed -i '' '/DROP EXTENSION/d' "$OUTPUT_FILE"
    sed -i '' '/ALTER EXTENSION/d' "$OUTPUT_FILE"
    # Remove RLS disable statements (RLS should always be enabled in production)
    sed -i '' '/DISABLE ROW LEVEL SECURITY/d' "$OUTPUT_FILE"
else
    # Remove Supabase schema drops
    sed -i '/DROP SCHEMA IF EXISTS \(auth\|storage\|realtime\|vault\)/d' "$OUTPUT_FILE"
    # Remove extension changes (extensions managed separately)
    sed -i '/CREATE EXTENSION/d' "$OUTPUT_FILE"
    sed -i '/DROP EXTENSION/d' "$OUTPUT_FILE"
    sed -i '/ALTER EXTENSION/d' "$OUTPUT_FILE"
    # Remove RLS disable statements (RLS should always be enabled in production)
    sed -i '/DISABLE ROW LEVEL SECURITY/d' "$OUTPUT_FILE"
fi

# Check if empty
if [ ! -s "$OUTPUT_FILE" ]; then
    echo "✨ No schema differences found."
    rm "$OUTPUT_FILE"
else
    echo "✅ Migration generated: $OUTPUT_FILE"
    echo "   ⚠️  ALWAYS review this file before applying!"
fi
