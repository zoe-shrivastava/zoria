#!/bin/bash
# Script to run migration 018 (child_preferences_cultural)
# Adds preferred_language and other preference columns to children table.
# Required for: Child profile (My Profile), language dropdown, study preferences.

echo "Running migration 018: child_preferences_cultural"

# Option 1: Using Docker (Recommended)
if command -v docker-compose &> /dev/null; then
    echo "Using Docker to run migration..."
    cd "$(dirname "$0")/../.."
    
    # Run migration via psql
    docker-compose exec -T postgres psql -U zoria -d zoria < backend/database/migrations/018_child_preferences_cultural.sql
    
    # Mark as applied
    docker-compose exec -T postgres psql -U zoria -d zoria -c "INSERT INTO schema_migrations (migration_name) VALUES ('018_child_preferences_cultural.sql') ON CONFLICT DO NOTHING;"
    
    echo "✅ Migration 018 completed"
    
# Option 2: Direct psql
elif command -v psql &> /dev/null; then
    echo "Using direct psql connection..."
    
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    DB_NAME=${DB_NAME:-zoria}
    DB_USER=${DB_USER:-zoria}
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$(dirname "$0")/migrations/018_child_preferences_cultural.sql"
    
    psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "INSERT INTO schema_migrations (migration_name) VALUES ('018_child_preferences_cultural.sql') ON CONFLICT DO NOTHING;"
    
    echo "✅ Migration 018 completed"
    
else
    echo "❌ Error: Neither docker-compose nor psql found"
    echo "Run the SQL manually: backend/database/migrations/018_child_preferences_cultural.sql"
    exit 1
fi
