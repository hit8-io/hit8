# Atlas Database Schema Management

This project uses [Atlas](https://atlasgo.io) for declarative database schema management.

## Quick Start

**Note:** All commands use `--schema public` to only manage the public schema, automatically excluding all Supabase system schemas.

### Dev Environment (No Doppler)
```bash
atlas schema apply \
  --to file://schema.hcl \
  --url "postgresql://postgres:postgres@localhost:54325/postgres?sslmode=disable&search_path=public" \
  --schema public
```

### Staging/Production (With Doppler)
```bash
# Staging
doppler run --config stg -- \
  sh -c 'atlas schema apply --to file://schema.hcl --url "$DIRECT_DB_CONNECTION_STRING" --schema public'

# Production
doppler run --config prd -- \
  sh -c 'atlas schema apply --to file://schema.hcl --url "$DIRECT_DB_CONNECTION_STRING" --schema public'
```

**How it works:**
- No config file needed - all settings via command-line flags
- `--to file://schema.hcl` specifies the desired schema state
- `--url` specifies the target database connection string
- `doppler run --config <env>` injects `DIRECT_DB_CONNECTION_STRING` as an environment variable

## Setup

### Install Atlas CLI

```bash
# macOS/Linux
curl -sSf https://atlasgo.sh | sh

# Or via Homebrew
brew install ariga/tap/atlas

# Verify installation
atlas version
```

## Development Workflow

### Making Schema Changes

1. Edit `database/schema.hcl` to reflect desired database changes
2. Review the diff (dry-run):
   ```bash
   # Dev: No Doppler needed (hardcoded connection)
   atlas schema apply \
     --to file://schema.hcl \
     --url "postgresql://postgres:postgres@localhost:54325/postgres?sslmode=disable&search_path=public" \
     --schema public \
     --dry-run
   ```
3. Apply the changes:
   ```bash
   # Dev: No Doppler needed
   atlas schema apply \
     --to file://schema.hcl \
     --url "postgresql://postgres:postgres@localhost:54325/postgres?sslmode=disable&search_path=public" \
     --schema public
   ```
4. Commit `database/schema.hcl` changes to Git

### View Schema Diff

```bash
# Dev: No Doppler needed
atlas schema apply \
  --to file://schema.hcl \
  --url "postgresql://postgres:postgres@localhost:54325/postgres?sslmode=disable&search_path=public" \
  --schema public \
  --dry-run

# Staging: Use Doppler to inject connection string
doppler run --config stg -- \
  sh -c 'atlas schema apply --to file://schema.hcl --url "$DIRECT_DB_CONNECTION_STRING" --schema public --dry-run'

# Production: Use Doppler to inject connection string
doppler run --config prd -- \
  sh -c 'atlas schema apply --to file://schema.hcl --url "$DIRECT_DB_CONNECTION_STRING" --schema public --dry-run'
```

### Apply Schema to Database

```bash
# Dev: No Doppler needed (hardcoded local connection)
atlas schema apply \
  --to file://schema.hcl \
  --url "postgresql://postgres:postgres@localhost:54325/postgres?sslmode=disable&search_path=public" \
  --schema public

# Staging: Use Doppler to inject DIRECT_DB_CONNECTION_STRING
doppler run --config stg -- \
  sh -c 'atlas schema apply --to file://schema.hcl --url "$DIRECT_DB_CONNECTION_STRING" --schema public'

# Production: Use Doppler to inject DIRECT_DB_CONNECTION_STRING
doppler run --config prd -- \
  sh -c 'atlas schema apply --to file://schema.hcl --url "$DIRECT_DB_CONNECTION_STRING" --schema public'
```

## Configuration

- `database/schema.hcl` - Declarative schema definition (desired database state)

Connection strings are passed via `--url` flag. For staging/production, use Doppler to inject `DIRECT_DB_CONNECTION_STRING`.

## CI/CD

Schema changes are automatically validated and applied in CI/CD via GitHub Actions. See `.github/workflows/deploy.yaml` for details.
