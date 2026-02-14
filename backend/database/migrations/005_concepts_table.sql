-- Migration 005: Create concepts table
-- Stores structured learning concepts extracted from documents

CREATE TABLE IF NOT EXISTS concepts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    subtopic TEXT,
    difficulty VARCHAR(20) CHECK (difficulty IN ('easy', 'medium', 'hard')),
    grade INT[],
    prerequisites TEXT[],
    keywords TEXT[],
    source_markdown TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_concepts_document_id ON concepts(document_id);
CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name);
CREATE INDEX IF NOT EXISTS idx_concepts_grade ON concepts USING GIN(grade);
CREATE INDEX IF NOT EXISTS idx_concepts_difficulty ON concepts(difficulty);
CREATE INDEX IF NOT EXISTS idx_concepts_keywords ON concepts USING GIN(keywords);
CREATE INDEX IF NOT EXISTS idx_concepts_prerequisites ON concepts USING GIN(prerequisites);
CREATE INDEX IF NOT EXISTS idx_concepts_subtopic ON concepts(subtopic);

-- Create composite index for common queries
CREATE INDEX IF NOT EXISTS idx_concepts_document_grade ON concepts(document_id, grade);

-- Add trigger for updated_at timestamp
CREATE TRIGGER update_concepts_updated_at 
    BEFORE UPDATE ON concepts
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE concepts IS 'Structured learning concepts extracted from educational documents';
COMMENT ON COLUMN concepts.grade IS 'Array of grade levels this concept targets (e.g., [6,7,8])';
COMMENT ON COLUMN concepts.prerequisites IS 'Array of prerequisite concept names';
COMMENT ON COLUMN concepts.keywords IS 'Array of keywords for semantic search';
COMMENT ON COLUMN concepts.source_markdown IS 'Original markdown text from which this concept was extracted';
COMMENT ON COLUMN concepts.difficulty IS 'Difficulty level: easy, medium, or hard';
