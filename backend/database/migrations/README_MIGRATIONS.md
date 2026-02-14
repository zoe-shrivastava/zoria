# Database Migrations Guide

## Overview

This directory contains database migration scripts for the Zoria adaptive learning system. Migrations are numbered sequentially and should be run in order.

## Migration Files

### Existing Migrations
- `001_initial_schema.sql` - Initial database schema (parents, children, documents, chunks, quizzes)
- `002_default_admin.sql` - Creates default admin user
- `003_add_child_code.sql` - Adds child_code field to children table

### Phase 1: Adaptive Learning Schema (NEW)

- **`004_document_status_metadata.sql`**
  - Adds status field to documents (uploaded → parsed → processing → ready/failed)
  - Adds metadata fields (source_type, grade_range, parser_version, etc.)
  - Updates existing documents to appropriate status

- **`005_concepts_table.sql`**
  - Creates concepts table for structured learning concepts
  - Includes grade arrays, difficulty, prerequisites, keywords
  - Indexes for efficient querying

- **`006_questions_table.sql`**
  - Creates questions table linked to concepts
  - Supports multiple question types (multiple_choice, short_answer, problem_solving, etc.)
  - Difficulty tracking

- **`007_visuals_table.sql`**
  - Creates visuals table for graphs, diagrams, images
  - Supports LaTeX code and JSON representations
  - Links to concepts and questions

- **`008_content_chunks_table.sql` ⚠️ CRITICAL**
  - Creates content_chunks table for embeddings
  - Uses pgvector with vector(1024) for mxbai-embed-large (Ollama)
  - Rich metadata for adaptive filtering

- **`009_knowledge_graph_tables.sql`**
  - Creates skills table for cognitive skills
  - Creates concept_relationships for prerequisites
  - Creates question_skills and document_concepts junction tables

- **`010_mastery_tracking.sql`**
  - Creates student_concept_mastery table
  - Includes helper function for exponential moving average updates

## Running Migrations

### Option 1: Using Migration Script (Recommended)

If you have a migration runner script:

```bash
# From zoria/backend directory
python -m database.migrate
```

### Option 2: Manual Execution

```bash
# Connect to PostgreSQL
psql -U zoria -d zoria -h localhost

# Run migrations in order
\i database/migrations/004_document_status_metadata.sql
\i database/migrations/005_concepts_table.sql
\i database/migrations/006_questions_table.sql
\i database/migrations/007_visuals_table.sql
\i database/migrations/008_content_chunks_table.sql
\i database/migrations/009_knowledge_graph_tables.sql
\i database/migrations/010_mastery_tracking.sql
```

### Option 3: Using Docker

If running in Docker:

```bash
# Copy migrations into container and run
docker exec -i zoria-db psql -U zoria -d zoria < database/migrations/004_document_status_metadata.sql
# ... repeat for each migration
```

## Important Notes

### Embedding Dimension

The `content_chunks` table uses `vector(1024)` for mxbai-embed-large (Ollama).

**If you need to use a different model:**

1. Before running migration 008, edit the file to change the dimension:
   ```sql
   -- For bge-base-en-v1.5 (768 dimensions):
   embedding VECTOR(768),
   
   -- For bge-small-en-v1.5 (384 dimensions):
   embedding VECTOR(384),
   ```

2. Or after migration, run:
   ```sql
   DROP INDEX idx_content_chunks_embedding;
   ALTER TABLE content_chunks ALTER COLUMN embedding TYPE VECTOR(<new_dimension>);
   CREATE INDEX idx_content_chunks_embedding ON content_chunks 
       USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
   ```

### Migration Safety

All migrations use `IF NOT EXISTS` and `ADD COLUMN IF NOT EXISTS` to be idempotent. They can be run multiple times safely.

### Existing Data

- Migration 004 updates existing documents to have appropriate status
- Other migrations create new tables and won't affect existing data
- The existing `chunks` table remains unchanged (new `content_chunks` table is separate)

## Verification

After running migrations, verify with:

```sql
-- Check document status field
SELECT status, COUNT(*) FROM documents GROUP BY status;

-- Check new tables exist
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('concepts', 'questions', 'visuals', 'content_chunks', 'skills', 'student_concept_mastery');

-- Check indexes
SELECT indexname FROM pg_indexes 
WHERE tablename IN ('concepts', 'questions', 'content_chunks');

-- Check pgvector extension
SELECT * FROM pg_extension WHERE extname = 'vector';
```

## Rollback

If you need to rollback (⚠️ **DESTRUCTIVE**):

```sql
-- Remove new tables (in reverse order)
DROP TABLE IF EXISTS student_concept_mastery CASCADE;
DROP TABLE IF EXISTS document_concepts CASCADE;
DROP TABLE IF EXISTS question_skills CASCADE;
DROP TABLE IF EXISTS concept_relationships CASCADE;
DROP TABLE IF EXISTS skills CASCADE;
DROP TABLE IF EXISTS content_chunks CASCADE;
DROP TABLE IF EXISTS visuals CASCADE;
DROP TABLE IF EXISTS questions CASCADE;
DROP TABLE IF EXISTS concepts CASCADE;

-- Remove new columns from documents (if needed)
ALTER TABLE documents 
DROP COLUMN IF EXISTS status,
DROP COLUMN IF EXISTS source_type,
DROP COLUMN IF EXISTS grade_range,
DROP COLUMN IF EXISTS parser_version,
DROP COLUMN IF EXISTS concept_extractor_version,
DROP COLUMN IF EXISTS embedding_model,
DROP COLUMN IF EXISTS processing_started_at,
DROP COLUMN IF EXISTS processing_completed_at,
DROP COLUMN IF EXISTS failure_stage,
DROP COLUMN IF EXISTS error_message;
```

## Next Steps

After running migrations:

1. ✅ Verify all tables created successfully
2. ✅ Check indexes are created
3. ✅ Test pgvector extension is working
4. ➡️ Proceed to Phase 2: Implement core services (ChunkingService, EmbeddingService)

## Troubleshooting

### Error: "extension vector does not exist"
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Error: "column already exists"
This is safe to ignore - migrations use `IF NOT EXISTS` clauses.

### Error: "relation already exists"
The table already exists. Check if migration was partially run.

### Performance: Slow index creation
The ivfflat index on `content_chunks.embedding` may take time for large datasets. This is normal.
