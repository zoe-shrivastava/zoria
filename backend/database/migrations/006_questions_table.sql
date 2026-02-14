-- Migration 006: Create questions table
-- Stores individual questions extracted from documents, linked to concepts

CREATE TABLE IF NOT EXISTS questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    type VARCHAR(50) CHECK (type IN (
        'multiple_choice', 
        'short_answer', 
        'problem_solving', 
        'conceptual_question',
        'matching',
        'fill_in_the_blank'
    )),
    difficulty VARCHAR(20) CHECK (difficulty IN ('easy', 'medium', 'hard')),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_questions_concept_id ON questions(concept_id);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(type);
CREATE INDEX IF NOT EXISTS idx_questions_difficulty ON questions(difficulty);
CREATE INDEX IF NOT EXISTS idx_questions_metadata ON questions USING GIN(metadata);

-- Create composite index for common queries (concept + difficulty)
CREATE INDEX IF NOT EXISTS idx_questions_concept_difficulty ON questions(concept_id, difficulty);

-- Add comments for documentation
COMMENT ON TABLE questions IS 'Individual questions extracted from documents, linked to concepts';
COMMENT ON COLUMN questions.type IS 'Type of question: multiple_choice, short_answer, problem_solving, etc.';
COMMENT ON COLUMN questions.difficulty IS 'Difficulty level: easy, medium, or hard';
COMMENT ON COLUMN questions.metadata IS 'Additional question metadata (options, correct_answer, visual_id, etc.)';
