-- Migration 020: Immutable KG snapshots per processing run
-- Stores run-scoped KG payloads for reproducible evaluation/testing.

CREATE TABLE IF NOT EXISTS kg_run_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    run_type VARCHAR(30) NOT NULL CHECK (run_type IN ('ingestion', 'rebuild', 'reprocess')),
    snapshot_source VARCHAR(50) NOT NULL DEFAULT 'from_concepts_json',
    concepts_json_hash TEXT,
    kg_payload JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_kg_run_snapshots_document_created
    ON kg_run_snapshots(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_kg_run_snapshots_run_type
    ON kg_run_snapshots(run_type);

COMMENT ON TABLE kg_run_snapshots IS 'Immutable KG snapshots captured per processing run for accuracy testing';
COMMENT ON COLUMN kg_run_snapshots.kg_payload IS 'Frozen run-scoped KG payload (nodes, edges, counts, distributions)';
