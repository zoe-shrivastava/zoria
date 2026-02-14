-- Migration 013: Add embedding field to questions table for semantic deduplication

-- Add embedding column (using pgvector)
ALTER TABLE questions 
ADD COLUMN IF NOT EXISTS embedding vector(1024);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_questions_embedding 
ON questions 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Add status field to track question generation status
ALTER TABLE questions 
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'verified' 
CHECK (status IN ('generated', 'verified', 'rejected'));

-- Add index for status filtering
CREATE INDEX IF NOT EXISTS idx_questions_status ON questions(status);

-- Add composite index for common queries (concept + difficulty + status)
CREATE INDEX IF NOT EXISTS idx_questions_concept_difficulty_status 
ON questions(concept_id, difficulty, status) 
WHERE status != 'rejected';

COMMENT ON COLUMN questions.embedding IS 'Vector embedding for semantic similarity search and deduplication';
COMMENT ON COLUMN questions.status IS 'Question status: generated (newly created), verified (approved), rejected (duplicate/low quality)';
