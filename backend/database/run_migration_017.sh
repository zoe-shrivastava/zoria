#!/bin/bash
# Script to run migration 017 (study_guides_table)

echo "Running migration 017: study_guides_table"

# Option 1: Using Docker (Recommended)
if command -v docker-compose &> /dev/null; then
    echo "Using Docker to run migration..."
    cd "$(dirname "$0")/../.."
    
    # Make sure postgres is running
    docker-compose up -d postgres
    sleep 3
    
    # Run migration via psql
    docker-compose exec -T postgres psql -U zoria -d zoria < backend/database/migrations/017_study_guides_table.sql
    
    # Mark as applied
    docker-compose exec -T postgres psql -U zoria -d zoria -c "INSERT INTO schema_migrations (migration_name) VALUES ('017_study_guides_table.sql') ON CONFLICT DO NOTHING;"
    
    echo "✅ Migration 017 completed"
    
# Option 2: Direct psql
elif command -v psql &> /dev/null; then
    echo "Using direct psql connection..."
    
    # Set these environment variables or modify as needed
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    DB_NAME=${DB_NAME:-zoria}
    DB_USER=${DB_USER:-zoria}
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$(dirname "$0")/migrations/017_study_guides_table.sql"
    
    # Mark as applied
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "INSERT INTO schema_migrations (migration_name) VALUES ('017_study_guides_table.sql') ON CONFLICT DO NOTHING;"
    
    echo "✅ Migration 017 completed"
    
else
    echo "❌ Error: Neither docker-compose nor psql found"
    echo "Please run the migration manually using one of the methods in RUN_MIGRATIONS.md"
    exit 1
fi
