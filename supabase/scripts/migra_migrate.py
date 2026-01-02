#!/usr/bin/env python3
"""
Migra-based database migration script.

Usage:
    doppler run --config prd -- python supabase/scripts/migra_migrate.py [--dry-run] [--env ENV]
"""
from __future__ import annotations

import argparse
import os
import sys

import structlog
import psycopg
from migra import Migration
from sqlalchemy import text
from sqlbag import S

logger = structlog.get_logger(__name__)

DEFAULT_DEV_DB = "postgresql://postgres:postgres@localhost:5432/hit8?sslmode=disable"
SCHEMA = "public"
SUPABASE_SCHEMAS = {"auth", "storage", "realtime", "vault", "extensions", "pg_graphql", 
                    "pg_stat_statements", "supabase_vault", "pgbouncer", "graphql"}


def get_database_urls(env: str) -> tuple[str, str]:
    """Get dev and production database URLs. Both use 'public' schema."""
    if env == "prd":
        prd_db_url = os.getenv("DATABASE_CONNECTION_STRING")
        if not prd_db_url:
            raise ValueError("DATABASE_CONNECTION_STRING required. Use: doppler run --config prd -- ...")
        return os.getenv("DEV_DATABASE_CONNECTION_STRING", DEFAULT_DEV_DB), prd_db_url
    elif env == "dev":
        return DEFAULT_DEV_DB, os.getenv("DATABASE_CONNECTION_STRING", DEFAULT_DEV_DB)
    raise ValueError(f"Unknown environment: {env}")


def add_search_path(url: str, schema: str) -> str:
    """Add search_path to connection string."""
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}options=-csearch_path%3D{schema}"


def filter_sql(sql: str) -> str:
    """Filter out Supabase schema changes and extension updates from migration SQL."""
    lines = []
    for line in sql.split("\n"):
        line_lower = line.lower()
        # Skip Supabase schemas, schema drops, extension drops, and extension updates
        if (any(schema in line_lower for schema in SUPABASE_SCHEMAS) or
            line.strip().startswith(("drop schema", "drop extension", "alter extension"))):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def get_new_tables_from_sql(sql: str, schema: str = SCHEMA) -> list[str]:
    """Extract table names from CREATE TABLE statements in migration SQL."""
    import re
    
    pattern = rf'create\s+table\s+(?:"?{re.escape(schema)}"?"?\.)?"?(\w+)"?'
    tables = re.findall(pattern, sql, re.IGNORECASE)
    # Remove duplicates while preserving order
    return list(dict.fromkeys(table.lower() for table in tables))


def enable_rls_on_tables(prd_db_url: str, tables: list[str], schema: str = SCHEMA, dry_run: bool = False) -> bool:
    """Enable RLS on specified tables using psycopg."""
    if not tables:
        return True
    
    try:
        with psycopg.connect(prd_db_url) as conn:
            with conn.cursor() as cur:
                print(f"\n-- Enabling RLS on {len(tables)} table(s) in '{schema}' schema:")
                for table in tables:
                    rls_stmt = f'ALTER TABLE "{schema}"."{table}" ENABLE ROW LEVEL SECURITY;'
                    print(f"  {rls_stmt}")
                    
                    if not dry_run:
                        cur.execute(rls_stmt)
                
                if not dry_run:
                    conn.commit()
                    print(f"✓ RLS enabled on {len(tables)} table(s)")
                else:
                    print("✓ Dry-run complete - RLS not applied")
                return True
                
    except Exception as e:
        logger.exception("rls_enable_failed", error=str(e), error_type=type(e).__name__)
        print(f"\n✗ Failed to enable RLS: {e}")
        return False


def get_tables_without_rls(prd_db_url: str, schema: str = SCHEMA) -> list[str]:
    """Get all tables in schema that don't have RLS enabled."""
    try:
        with psycopg.connect(prd_db_url) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.tablename 
                    FROM pg_tables t
                    JOIN pg_class c ON c.relname = t.tablename
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = %s
                    AND t.schemaname = %s
                    AND c.relkind = 'r'
                    AND c.relrowsecurity = false
                    ORDER BY t.tablename;
                """, (schema, schema))
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        logger.exception("get_tables_failed", error=str(e), error_type=type(e).__name__)
        return []


def run_migration(dev_db_url: str, prd_db_url: str, dry_run: bool = False, env: str = "prd") -> bool:
    """Run migration using Migra to compare dev and production databases."""
    try:
        with S(add_search_path(dev_db_url, SCHEMA)) as dev_db, S(add_search_path(prd_db_url, SCHEMA)) as prd_db:
            migration = Migration(prd_db, dev_db)
            migration.add_all_changes()
            migration.set_safety(False)
            
            migration_sql = filter_sql(migration.sql)
            
            if not migration_sql:
                print("✓ No changes detected - databases are already in sync")
                if env == "prd":
                    existing_tables = get_tables_without_rls(prd_db_url, SCHEMA)
                    if existing_tables:
                        enable_rls_on_tables(prd_db_url, existing_tables, SCHEMA, dry_run)
                    else:
                        print("✓ All tables already have RLS enabled")
                return True
            
            new_tables = get_new_tables_from_sql(migration_sql, SCHEMA)
            
            print("\n" + "=" * 50)
            print(f"Migration SQL ({SCHEMA} schema):")
            print("=" * 50)
            print(migration_sql)
            print("=" * 50 + "\n")
            
            if dry_run:
                print("✓ Dry-run complete - no changes applied")
                if env == "prd":
                    existing_tables = get_tables_without_rls(prd_db_url, SCHEMA)
                    enable_rls_on_tables(prd_db_url, existing_tables, SCHEMA, dry_run=True)
                    enable_rls_on_tables(prd_db_url, new_tables, SCHEMA, dry_run=True)
                return True
            
            # Apply filtered migration SQL (to avoid extension update issues)
            if migration_sql:
                # Execute filtered SQL directly instead of using migration.apply()
                # This avoids issues with extension updates that require superuser privileges
                prd_db.execute(text(migration_sql))
                prd_db.commit()
            
            print("✓ Migration applied successfully")
            
            if env == "prd":
                existing_tables = get_tables_without_rls(prd_db_url, SCHEMA)
                if not enable_rls_on_tables(prd_db_url, existing_tables, SCHEMA, dry_run=False):
                    return False
                if not enable_rls_on_tables(prd_db_url, new_tables, SCHEMA, dry_run=False):
                    return False
            
            return True
            
    except Exception as e:
        logger.exception("migration_failed", error=str(e), error_type=type(e).__name__)
        print(f"\n✗ Migration failed: {e}")
        return False


def main() -> int:
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate database schema using Migra")
    parser.add_argument("--dry-run", action="store_true", help="Show SQL without applying")
    parser.add_argument("--env", choices=["dev", "prd"], default="prd", help="Environment (default: prd)")
    args = parser.parse_args()
    
    print("==========================================")
    print("Migra Migration")
    print(f"Environment: {args.env}")
    print(f"Mode: {'Dry-run' if args.dry_run else 'Apply'}")
    print("==========================================")
    print()
    
    try:
        dev_db_url, prd_db_url = get_database_urls(args.env)
        return 0 if run_migration(dev_db_url, prd_db_url, dry_run=args.dry_run, env=args.env) else 1
    except Exception as e:
        logger.exception("migration_error", error=str(e), error_type=type(e).__name__)
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

