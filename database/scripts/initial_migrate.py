#!/usr/bin/env python3
"""
Database migration script using pg_dump/pg_restore.

This script migrates both schema (structure) and data from dev to production.
By default, it migrates both. Use --schema-only or --data-only to migrate only one.

Usage:
    # Migrate both schema and data (default)
    doppler run --config prd -- python database/scripts/initial_migrate.py
    
    # Migrate schema only
    doppler run --config prd -- python database/scripts/initial_migrate.py --schema-only
    
    # Migrate data only
    doppler run --config prd -- python database/scripts/initial_migrate.py --data-only
    
    # Dry run
    doppler run --config prd -- python database/scripts/initial_migrate.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Hardcoded local dev connection string
# Uses default 'postgres' database
DEV_CONNECTION_STRING = "postgresql://postgres:postgres@localhost:5432/postgres"

# Production connection string from Doppler
PRD_CONNECTION_STRING = os.getenv("DATABASE_CONNECTION_STRING")
if not PRD_CONNECTION_STRING:
    raise ValueError(
        "DATABASE_CONNECTION_STRING environment variable is required. "
        "Use Doppler: doppler run --config prd -- python ..."
    )


def run_command(cmd: list[str], description: str) -> bool:
    """Run a shell command and log the result."""
    logger.info("running_command", command=" ".join(cmd), description=description)
    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            logger.debug("command_output", output=result.stdout[:500])  # Limit output
        return True
    except subprocess.CalledProcessError as e:
        logger.error(
            "command_failed",
            command=" ".join(cmd),
            error=e.stderr or str(e),
            returncode=e.returncode,
        )
        return False


def create_backup(prd_conn_string: str, backup_file: Path, schema: str = "public") -> bool:
    """Create backup using pg_dump."""
    logger.info("creating_backup", backup_file=str(backup_file))
    
    # pg_dump only schema and data for specified schema
    cmd = [
        "pg_dump",
        prd_conn_string,
        "--schema", schema,
        "--format", "custom",
        "--file", str(backup_file),
        "--verbose",
    ]
    
    return run_command(cmd, "Create backup")


def migrate_schema(
    dev_conn_string: str,
    prd_conn_string: str,
    dev_schema: str = "public",
    prd_schema: str = "public",
    dry_run: bool = False,
) -> bool:
    """Migrate schema using pg_dump --schema-only."""
    logger.info(
        "migrating_schema",
        dev_schema=dev_schema,
        prd_schema=prd_schema,
        dry_run=dry_run,
    )
    
    # Export schema from dev
    schema_file = Path("/tmp/migration_schema.sql")
    
    cmd_dump = [
        "pg_dump",
        dev_conn_string,
        "--schema", dev_schema,
        "--schema-only",  # Only structure, no data
        "--file", str(schema_file),
        "--verbose",
    ]
    
    if not run_command(cmd_dump, f"Export schema from dev ({dev_schema})"):
        return False
    
    if dry_run:
        logger.info("dry_run_skip_schema_import", schema_file=str(schema_file))
        return True
    
    # Read schema file and replace schema name if different
    schema_content = schema_file.read_text()
    if dev_schema != prd_schema:
        schema_content = schema_content.replace(f'"{dev_schema}".', f'"{prd_schema}".')
        schema_content = schema_content.replace(f"CREATE SCHEMA {dev_schema}", f"CREATE SCHEMA IF NOT EXISTS {prd_schema}")
        schema_content = schema_content.replace(f"SET search_path TO {dev_schema}", f"SET search_path TO {prd_schema}")
    # Fix vector type references: public.vector -> extensions.vector (vector extension is in extensions schema)
    schema_content = schema_content.replace("public.vector(", "extensions.vector(")
    schema_file.write_text(schema_content)
    
    # Import schema to production
    cmd_restore = [
        "psql",
        prd_conn_string,
        "--file", str(schema_file),
        "--quiet",
    ]
    
    return run_command(cmd_restore, f"Import schema to production ({prd_schema})")


def migrate_data(
    dev_conn_string: str,
    prd_conn_string: str,
    dev_schema: str = "public",
    prd_schema: str = "public",
    dry_run: bool = False,
) -> bool:
    """Migrate data using pg_dump --data-only."""
    logger.info(
        "migrating_data",
        dev_schema=dev_schema,
        prd_schema=prd_schema,
        dry_run=dry_run,
    )
    
    # Export data from dev
    data_file = Path("/tmp/migration_data.sql")
    
    cmd_dump = [
        "pg_dump",
        dev_conn_string,
        "--schema", dev_schema,
        "--data-only",  # Only data, no structure
        "--file", str(data_file),
        "--verbose",
    ]
    
    if not run_command(cmd_dump, f"Export data from dev ({dev_schema})"):
        return False
    
    if dry_run:
        logger.info("dry_run_skip_data_import", data_file=str(data_file))
        return True
    
    # Read data file and replace schema name if different
    data_content = data_file.read_text()
    if dev_schema != prd_schema:
        data_content = data_content.replace(f'"{dev_schema}".', f'"{prd_schema}".')
    data_file.write_text(data_content)
    
    # Import data to production
    cmd_restore = [
        "psql",
        prd_conn_string,
        "--file", str(data_file),
        "--quiet",
    ]
    
    return run_command(cmd_restore, f"Import data to production ({prd_schema})")


def main() -> int:
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate database using pg_dump/pg_restore")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actually importing",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip creating a backup before migration",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only migrate schema (structure), not data",
    )
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Only migrate data, not schema",
    )
    parser.add_argument(
        "--dev-schema",
        default="public",
        help="Source schema in dev database (default: public)",
    )
    parser.add_argument(
        "--prd-schema",
        default="public",
        help="Target schema in production database (default: public)",
    )
    args = parser.parse_args()
    
    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
    )
    
    logger.info(
        "migration_started",
        dry_run=args.dry_run,
        dev_schema=args.dev_schema,
        prd_schema=args.prd_schema,
    )
    
    try:
        # Create backup if not skipped
        backup_file = None
        if not args.skip_backup and not args.dry_run:
            backup_dir = Path(__file__).parent.parent / "backup"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_file = backup_dir / f"pre_migration_backup_{args.prd_schema}.dump"
            if not create_backup(PRD_CONNECTION_STRING, backup_file, args.prd_schema):
                logger.error("backup_failed", message="Backup failed, aborting migration")
                return 1
        
        # Migrate schema
        if not args.data_only:
            if not migrate_schema(
                DEV_CONNECTION_STRING,
                PRD_CONNECTION_STRING,
                args.dev_schema,
                args.prd_schema,
                args.dry_run,
            ):
                logger.error("schema_migration_failed")
                return 1
        
        # Migrate data
        if not args.schema_only:
            if not migrate_data(
                DEV_CONNECTION_STRING,
                PRD_CONNECTION_STRING,
                args.dev_schema,
                args.prd_schema,
                args.dry_run,
            ):
                logger.error("data_migration_failed")
                return 1
        
        logger.info(
            "migration_completed",
            dry_run=args.dry_run,
            dev_schema=args.dev_schema,
            prd_schema=args.prd_schema,
            backup_file=str(backup_file) if backup_file else None,
        )
        
        return 0
        
    except Exception as e:
        logger.error(
            "migration_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

