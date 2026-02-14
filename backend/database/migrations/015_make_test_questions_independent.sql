-- Migration 015: Make test_questions independent copies of questions
-- Test questions should be immutable snapshots, not references

-- Add columns to store question data directly
ALTER TABLE test_questions 
ADD COLUMN IF NOT EXISTS question_text TEXT,
ADD COLUMN IF NOT EXISTS question_type VARCHAR(50),
ADD COLUMN IF NOT EXISTS question_difficulty VARCHAR(20),
ADD COLUMN IF NOT EXISTS question_metadata JSONB,
ADD COLUMN IF NOT EXISTS original_question_id UUID REFERENCES questions(id) ON DELETE SET NULL;

-- Make question_id nullable (it's now just a reference, not required)
ALTER TABLE test_questions 
ALTER COLUMN question_id DROP NOT NULL;

-- Remove CASCADE constraint - we want to preserve test_questions even if questions are deleted
ALTER TABLE test_questions 
DROP CONSTRAINT IF EXISTS test_questions_question_id_fkey;

-- Add new foreign key with SET NULL instead of CASCADE
ALTER TABLE test_questions 
ADD CONSTRAINT test_questions_question_id_fkey 
FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL;

-- Update existing test_questions to copy question data
UPDATE test_questions tq
SET 
    question_text = q.text,
    question_type = q.type,
    question_difficulty = q.difficulty,
    question_metadata = q.metadata,
    original_question_id = q.id
FROM questions q
WHERE tq.question_id = q.id 
AND (tq.question_text IS NULL OR tq.question_metadata IS NULL);

-- Also update test_responses to preserve responses when questions are deleted
ALTER TABLE test_responses 
DROP CONSTRAINT IF EXISTS test_responses_question_id_fkey;

ALTER TABLE test_responses 
ADD CONSTRAINT test_responses_question_id_fkey 
FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE SET NULL;

-- Update UNIQUE constraint on test_questions to handle NULL question_id
-- PostgreSQL allows multiple NULLs in UNIQUE, but we'll add a partial unique index
-- to ensure uniqueness when question_id is not NULL
-- First drop the existing unique constraint if it exists
ALTER TABLE test_questions 
DROP CONSTRAINT IF EXISTS test_questions_test_id_question_id_key;

-- Create partial unique index for non-NULL question_ids
CREATE UNIQUE INDEX IF NOT EXISTS test_questions_test_id_question_id_unique 
ON test_questions(test_id, question_id) 
WHERE question_id IS NOT NULL;

-- Add unique constraint on (test_id, order_index) to prevent duplicates
CREATE UNIQUE INDEX IF NOT EXISTS test_questions_test_id_order_unique 
ON test_questions(test_id, order_index);

-- Add comments
COMMENT ON COLUMN test_questions.question_text IS 'Full question text (independent copy)';
COMMENT ON COLUMN test_questions.question_type IS 'Question type (multiple_choice, short_answer, etc.)';
COMMENT ON COLUMN test_questions.question_difficulty IS 'Question difficulty level';
COMMENT ON COLUMN test_questions.question_metadata IS 'Question metadata including options, correct_answer, etc.';
COMMENT ON COLUMN test_questions.original_question_id IS 'Reference to original question (nullable, for tracking only)';
COMMENT ON COLUMN test_questions.question_id IS 'Legacy reference (nullable, kept for backward compatibility)';
COMMENT ON TABLE test_questions IS 'Independent copies of questions for tests. Questions remain available even if original questions are deleted.';
