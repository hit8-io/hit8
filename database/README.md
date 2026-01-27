# Atlas Database Schema Management

This project uses [Atlas](https://atlasgo.io) for declarative database schema management with a modular schema structure.

## Quick Start

**Note:** All commands must be run from the `database/` directory so Atlas can auto-discover `atlas.hcl`. Atlas automatically manages the `hit8` schema.

### Dev Environment (No Doppler)

Dev environment uses a hardcoded connection string for localhost access:

```bash
cd database
atlas schema apply --env dev
```

### Staging/Production (With Doppler)

Staging and production environments use Doppler to inject connection strings:

```bash
# Staging
cd database
doppler run --config stg -- atlas schema apply --env stg

# Production
cd database
doppler run --config prd -- atlas schema apply --env prd
```

**How it works:**
- `atlas.hcl` is auto-discovered when running from the `database/` directory
- Schema source is loaded from `schemas/**/*.hcl` files using `fileset()`
- Dev environment has a hardcoded connection string in `atlas.hcl`
- Staging/production environments use `doppler run --config <env>` to inject `DIRECT_DB_CONNECTION_STRING`

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

## Schema Structure

The schema is organized modularly under `schemas/hit8/`:

```
database/
  atlas.hcl                    # Atlas project configuration
  schemas/
    hit8/
      schema.hcl               # Schema declaration
      tables/
        langgraph/
          checkpoints.hcl      # LangGraph checkpoint tables
        rag/
          proc.hcl             # Procedure document processing tables
          regel.hcl            # Regulation document processing tables
          entities_relationships.hcl  # Entity and relationship tables
        users/
          user_threads.hcl     # User thread management tables
```

This modular structure allows the schema to grow organically as new domains are added.

## Development Workflow

### Making Schema Changes

1. Edit schema files in `schemas/hit8/tables/` to reflect desired database changes
2. Review the diff (dry-run):
   ```bash
   cd database
   atlas schema apply --env dev --dry-run
   ```
3. Apply the changes:
   ```bash
   cd database
   atlas schema apply --env dev
   ```
4. Commit schema file changes to Git

### View Schema Diff

```bash
cd database

# Dev (no Doppler needed)
atlas schema apply --env dev --dry-run

# Staging (with Doppler)
doppler run --config stg -- atlas schema apply --env stg --dry-run

# Production (with Doppler)
doppler run --config prd -- atlas schema apply --env prd --dry-run
```

### Apply Schema to Database

```bash
cd database

# Dev (no Doppler needed)
atlas schema apply --env dev

# Staging (with Doppler)
doppler run --config stg -- atlas schema apply --env stg

# Production (with Doppler)
doppler run --config prd -- atlas schema apply --env prd
```

## Configuration

- `database/atlas.hcl` - Atlas project configuration with environment definitions
- `database/schemas/hit8/` - Modular schema files organized by domain
- `database/schema.hcl` - **Deprecated** - Kept for reference only, will be removed in a future cleanup

- **Dev**: Connection string is hardcoded in `atlas.hcl` for localhost access (no Doppler needed)
- **Staging/Production**: Connection strings are injected via Doppler's `DIRECT_DB_CONNECTION_STRING` environment variable

## CI/CD

Schema changes are automatically validated and applied in CI/CD via GitHub Actions. See `.github/workflows/deploy.yaml` for details.
