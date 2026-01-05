# Database Migrations

## Generate Migration

Generate a migration from your local database changes:

```bash
supabase db diff -f <migration_name>
```

The migration file will be created in `supabase/migrations/`. Review it, then commit to git.

## Apply Migrations to Production

Apply migrations to production using Doppler for secrets:

```bash
# Dry run (simulate without applying)
doppler run --config prd -- supabase db push --db-url "$DIRECT_DB_CONNECTION_STRING" --dry-run

# Apply migrations
doppler run --config prd -- supabase db push --db-url "$DIRECT_DB_CONNECTION_STRING"
```

**Note:** Migrations are performed manually outside of CI/CD. The `DIRECT_DB_CONNECTION_STRING` secret is available in Doppler.

