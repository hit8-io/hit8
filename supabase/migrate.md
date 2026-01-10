# Database Migrations

## Generate Migration

Generate a migration from your local database changes:

```bash
supabase db diff --use-pg-schema -f <migration_name>
```

The migration file will be created in `supabase/migrations/`. Review it, then commit to git.

**Note:** The `--use-pg-schema` flag is required because the default `migra` tool fails with a port conflict error ("Address already in use"). This is a known issue with Supabase CLI when running alongside a local Supabase instance. The `--use-pg-schema` flag uses an alternative schema comparison tool that avoids this conflict.

**Limitations:** The `--use-pg-schema` flag is experimental and may not include all database entities (such as views and grants). Review generated migrations carefully to ensure completeness.

## Apply Migrations to Production

Apply migrations to production using Doppler for secrets:

```bash
# Dry run (simulate without applying)
doppler run --config prd -- sh -c 'supabase db push --db-url "$DIRECT_DB_CONNECTION_STRING" --dry-run'

# Apply migrations
doppler run --config prd -- sh -c 'supabase db push --db-url "$DIRECT_DB_CONNECTION_STRING"'
```

**Note:** Migrations are performed manually outside of CI/CD. The `DIRECT_DB_CONNECTION_STRING` secret is available in Doppler.

