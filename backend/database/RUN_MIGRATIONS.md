# Running Database Migrations

**If Child "My Profile" fails with `column "preferred_language" does not exist`**, run migration 018:

```bash
cd zoria
docker-compose exec backend python database/migrate.py
# or run only 018:
./backend/database/run_migration_018.sh
```

## Option 1: Using Docker (Recommended)

### Run migrations inside the backend container:

```bash
# Make sure containers are running
cd /mnt/c/Krishna/projects/zbot/zoria
docker-compose up -d postgres

# Wait for postgres to be ready
sleep 5

# Run migrations inside the backend container
docker-compose exec backend python database/migrate.py
```

### Or run migrations directly via psql in postgres container:

```bash
# Connect to postgres container
docker-compose exec postgres psql -U zoria -d zoria

# Then run migrations manually:
\i /docker-entrypoint-initdb.d/004_document_status_metadata.sql
\i /docker-entrypoint-initdb.d/005_concepts_table.sql
\i /docker-entrypoint-initdb.d/006_questions_table.sql
\i /docker-entrypoint-initdb.d/007_visuals_table.sql
\i /docker-entrypoint-initdb.d/008_content_chunks_table.sql
\i /docker-entrypoint-initdb.d/009_knowledge_graph_tables.sql
\i /docker-entrypoint-initdb.d/010_mastery_tracking.sql
```

## Option 2: Using Python Script (Local)

If you have a local Python environment with dependencies:

```bash
cd /mnt/c/Krishna/projects/zbot/zoria/backend

# Install dependencies if needed
pip install asyncpg python-dotenv

# Set environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=zoria
export DB_USER=zoria
export DB_PASSWORD=zoria_password

# Run migrations
python database/migrate.py
```

## Option 3: Manual SQL Execution

Connect to your database and run each migration file in order:

```bash
# Connect to database
psql -h localhost -U zoria -d zoria

# Or via Docker:
docker-compose exec postgres psql -U zoria -d zoria
```

Then execute each migration:

```sql
-- 1. Create migration tracking table (if not exists)
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Run migrations (copy and paste each file's contents)
-- Start with 004_document_status_metadata.sql
-- Then 005_concepts_table.sql
-- ... and so on

-- 3. Mark migrations as applied (optional, for tracking)
INSERT INTO schema_migrations (migration_name) VALUES 
    ('004_document_status_metadata.sql'),
    ('005_concepts_table.sql'),
    ('006_questions_table.sql'),
    ('007_visuals_table.sql'),
    ('008_content_chunks_table.sql'),
    ('009_knowledge_graph_tables.sql'),
    ('010_mastery_tracking.sql')
ON CONFLICT DO NOTHING;
```

## Verification

After running migrations, verify they were applied:

```sql
-- Check migration tracking
SELECT * FROM schema_migrations ORDER BY migration_name;

-- Check new tables exist
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN (
    'concepts', 
    'questions', 
    'visuals', 
    'content_chunks', 
    'skills', 
    'student_concept_mastery'
);

-- Check document status column
SELECT column_name, data_type FROM information_schema.columns 
WHERE table_name = 'documents' 
AND column_name IN ('status', 'grade_range', 'source_type');

-- Check content_chunks embedding dimension
SELECT column_name, udt_name, character_maximum_length 
FROM information_schema.columns 
WHERE table_name = 'content_chunks' 
AND column_name = 'embedding';
```

## Troubleshooting

### Error: "relation already exists"
- This is safe to ignore - migrations use `IF NOT EXISTS`
- The migration was likely already applied

### Error: "extension vector does not exist"
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Error: "column already exists"
- The column was already added
- Safe to continue

### Error: "permission denied"
- Make sure you're using the correct database user
- Check database connection credentials

## Quick Test Command

Run this to test all migrations at once via Docker:

```bash
cd /mnt/c/Krishna/projects/zbot/zoria

# Start postgres
docker-compose up -d postgres

# Wait for it to be ready
sleep 5

# Run all migrations via psql
for migration in backend/database/migrations/00*.sql; do
    echo "Running $migration..."
    docker-compose exec -T postgres psql -U zoria -d zoria < "$migration"
done
```

## Database Cleanup

### Cleanup Orphaned Data

After deleting documents and tests, you may have orphaned records. Use the cleanup script to remove them:

```bash
# Via Docker (Recommended)
cd /mnt/c/Krishna/projects/zbot/zoria
docker-compose exec backend python database/cleanup_orphaned_data.py

# Or locally
cd zoria/backend
python database/cleanup_orphaned_data.py
```

**What it cleans:**
- Orphaned test_questions and test_responses (from deleted tests)
- Orphaned questions (from deleted concepts)
- Orphaned concepts (from deleted documents)
- Orphaned visuals, content_chunks, chunks
- Orphaned concept_relationships, question_skills
- Orphaned student_concept_mastery records
- Unused skills

**Safety:**
- Runs in a transaction (can rollback if needed)
- Preserves user data (parents, children)
- Preserves LLM logs (for auditing)
- Includes verification queries to check results

**Note:** This script is safe to run multiple times - it only deletes orphaned records.
```
