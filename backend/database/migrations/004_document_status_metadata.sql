-- Migration 004: Add document status and metadata fields
-- This enables status-driven lifecycle management for document processing

-- Add status field with check constraint
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'uploaded' 
  CHECK (status IN ('uploaded', 'parsed', 'processing', 'ready', 'failed'));

-- Add source type field
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS source_type VARCHAR(50);  -- pdf, image, worksheet

-- Add grade range as integer array
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS grade_range INT[];

-- Add subject field (if not already exists from other migrations)
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS subject VARCHAR(255);

-- Add processing metadata fields
ALTER TABLE documents 
ADD COLUMN IF NOT EXISTS parser_version VARCHAR(50),
ADD COLUMN IF NOT EXISTS concept_extractor_version VARCHAR(50),
ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(100),
ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS failure_stage VARCHAR(100),
ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_grade_range ON documents USING GIN(grade_range);
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_subject ON documents(subject);

-- Update existing documents to have 'ready' status if they have markdown_content
-- This handles existing documents that were processed before status tracking
DO $$
BEGIN
    UPDATE documents 
    SET status = 'ready'
    WHERE status IS NULL 
      AND markdown_content IS NOT NULL 
      AND markdown_content != '';
    
    -- Set status to 'uploaded' for documents without content
    UPDATE documents 
    SET status = 'uploaded'
    WHERE status IS NULL;
END $$;

-- Add comment for documentation
COMMENT ON COLUMN documents.status IS 'Document processing status: uploaded -> parsed -> processing -> ready/failed';
COMMENT ON COLUMN documents.grade_range IS 'Array of grade levels this document targets (e.g., [6,7,8])';
COMMENT ON COLUMN documents.source_type IS 'Type of source document: pdf, image, or worksheet';
