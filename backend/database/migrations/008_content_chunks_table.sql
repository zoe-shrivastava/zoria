-- Migration 008: Create content_chunks table
-- CRITICAL: This table stores embeddings for semantic search with rich metadata
-- Supports adaptive learning through metadata-based filtering

-- Note: Using vector(1024) for mxbai-embed-large (Ollama)
-- This matches the current embedding model configuration

CREATE TABLE IF NOT EXISTS content_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    concept_id UUID REFERENCES concepts(id) ON DELETE SET NULL,
    question_id UUID REFERENCES questions(id) ON DELETE SET NULL,
    chunk_type VARCHAR(50) NOT NULL CHECK (chunk_type IN (
        'concept_overview', 
        'explanation', 
        'question', 
        'visual_description',
        'section'
    )),
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1024),  -- mxbai-embed-large dimension
    metadata JSONB NOT NULL DEFAULT '{}',  -- Critical for adaptive filtering
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_content_chunks_document_id ON content_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_content_chunks_concept_id ON content_chunks(concept_id);
CREATE INDEX IF NOT EXISTS idx_content_chunks_question_id ON content_chunks(question_id);
CREATE INDEX IF NOT EXISTS idx_content_chunks_type ON content_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_content_chunks_metadata ON content_chunks USING GIN(metadata);

-- Create vector similarity index for fast semantic search
-- Using ivfflat index with 100 lists (adjust based on data size)
CREATE INDEX IF NOT EXISTS idx_content_chunks_embedding ON content_chunks 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Create composite indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_content_chunks_doc_type ON content_chunks(document_id, chunk_type);
CREATE INDEX IF NOT EXISTS idx_content_chunks_concept_type ON content_chunks(concept_id, chunk_type);

-- Add comments for documentation
COMMENT ON TABLE content_chunks IS 'Embedded content chunks for semantic search with adaptive learning metadata';
COMMENT ON COLUMN content_chunks.chunk_type IS 'Type of chunk: concept_overview, explanation, question, visual_description, or section';
COMMENT ON COLUMN content_chunks.embedding IS 'Vector embedding for semantic similarity search (dimension: 1024 for mxbai-embed-large)';
COMMENT ON COLUMN content_chunks.metadata IS 'JSONB metadata for adaptive filtering (grade, difficulty, keywords, prerequisites, etc.)';
COMMENT ON COLUMN content_chunks.chunk_text IS 'The actual text content of the chunk';

-- Note: If you need to change embedding dimension later, you'll need to:
-- 1. Drop the index: DROP INDEX idx_content_chunks_embedding;
-- 2. Alter the column: ALTER TABLE content_chunks ALTER COLUMN embedding TYPE VECTOR(<new_dimension>);
-- 3. Recreate the index: CREATE INDEX idx_content_chunks_embedding ON content_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
