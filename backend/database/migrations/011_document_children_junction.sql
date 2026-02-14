-- Migration 011: Create document_children junction table for many-to-many relationship
-- Allows one document to be attached to multiple child profiles

-- Create junction table
CREATE TABLE IF NOT EXISTS document_children (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    child_id UUID REFERENCES children(id) ON DELETE CASCADE,
    attached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    attached_by UUID REFERENCES parents(id) ON DELETE SET NULL, -- Who attached it
    PRIMARY KEY (document_id, child_id)
);

CREATE INDEX IF NOT EXISTS idx_document_children_document ON document_children(document_id);
CREATE INDEX IF NOT EXISTS idx_document_children_child ON document_children(child_id);
CREATE INDEX IF NOT EXISTS idx_document_children_attached_by ON document_children(attached_by);

-- Migrate existing data: create entries for documents that have child_id
INSERT INTO document_children (document_id, child_id, attached_at)
SELECT id, child_id, uploaded_at
FROM documents
WHERE child_id IS NOT NULL
  AND id NOT IN (SELECT document_id FROM document_children);

-- Add comment for documentation
COMMENT ON TABLE document_children IS 'Many-to-many relationship between documents and children. One document can be attached to multiple child profiles.';
COMMENT ON COLUMN document_children.attached_by IS 'Parent who attached this document to the child profile';
