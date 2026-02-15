-- Migration 016: Add behavioral tracking and evaluation metadata to test_responses
-- Enables storage of behavioral data (latency, edits, hints, confidence) and evaluation results

-- Add metadata JSONB column to test_responses for behavioral data and evaluation results
ALTER TABLE test_responses 
ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Create index on metadata for efficient querying
CREATE INDEX IF NOT EXISTS idx_test_responses_metadata 
ON test_responses USING GIN(metadata);

-- Add comments
COMMENT ON COLUMN test_responses.metadata IS 'Behavioral tracking data (latency_ms, edit_count, hints_accessed, confidence_score) and evaluation results (error_type, misconception, method_detected)';
