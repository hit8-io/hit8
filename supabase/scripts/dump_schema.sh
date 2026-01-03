#!/bin/bash
set -e

# Configuration
LOCAL_DB_URL="postgres://postgres:postgres@localhost:5432/postgres"
OUTPUT_FILE="../schema/10_schema.sql"

echo "💾 Dumping Public Schema to $OUTPUT_FILE..."

# Dump only the 'public' schema (Tables, Indexes, Policies, Functions)
# --no-owner/--no-privileges: Keeps the file clean of role-specific noise
# --clean --if-exists: Ensures the file is a complete replacement instruction
pg_dump "$LOCAL_DB_URL" \
  --schema=public \
  --schema-only \
  --no-owner \
  --no-privileges \
  --clean \
  --if-exists \
  --quote-all-identifiers \
  > "$OUTPUT_FILE"

# Remove pg_dump-specific commands that pg-schema-diff can't parse
sed -i.bak '/^\\restrict/d' "$OUTPUT_FILE" 2>/dev/null || \
sed -i '' '/^\\restrict/d' "$OUTPUT_FILE"
sed -i.bak '/^\\unrestrict/d' "$OUTPUT_FILE" 2>/dev/null || \
sed -i '' '/^\\unrestrict/d' "$OUTPUT_FILE"

# Remove PostgreSQL version-specific settings that may not be supported
sed -i.bak '/^SET transaction_timeout/d' "$OUTPUT_FILE" 2>/dev/null || \
sed -i '' '/^SET transaction_timeout/d' "$OUTPUT_FILE"

# Remove DROP SCHEMA statements (pg-schema-diff temp database needs public schema to exist)
sed -i.bak '/^DROP SCHEMA IF EXISTS "public"/d' "$OUTPUT_FILE" 2>/dev/null || \
sed -i '' '/^DROP SCHEMA IF EXISTS "public"/d' "$OUTPUT_FILE"

# Remove CREATE SCHEMA statements (temp database already has public schema)
sed -i.bak '/^CREATE SCHEMA "public"/d' "$OUTPUT_FILE" 2>/dev/null || \
sed -i '' '/^CREATE SCHEMA "public"/d' "$OUTPUT_FILE"

# Add extension creation (needed for pg-schema-diff temp database)
# Insert before search_path is cleared, and set search_path after
if ! grep -q "CREATE EXTENSION IF NOT EXISTS vector" "$OUTPUT_FILE"; then
    # Use a temporary file for cross-platform compatibility
    TEMP_FILE="${OUTPUT_FILE}.tmp"
    awk '/^SET client_encoding/ { 
        print; 
        print "CREATE EXTENSION IF NOT EXISTS vector;"; 
        next 
    } 
    /^SELECT pg_catalog.set_config.*search_path.*false/ {
        print;
        print "SET search_path = public;";
        next
    }
    1' "$OUTPUT_FILE" > "$TEMP_FILE"
    mv "$TEMP_FILE" "$OUTPUT_FILE"
fi

# Fix vector type references (remove schema prefix for pg-schema-diff compatibility)
sed -i.bak 's/"public"\."vector"/vector/g' "$OUTPUT_FILE" 2>/dev/null || \
sed -i '' 's/"public"\."vector"/vector/g' "$OUTPUT_FILE"

rm -f "${OUTPUT_FILE}.bak" 2>/dev/null || true

echo "✅ Schema snapshot updated. You can now 'git add' the schema file."

