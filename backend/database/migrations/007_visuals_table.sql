-- Migration 007: Create visuals table
-- Stores visual descriptions, graphs, diagrams, and their representations

CREATE TABLE IF NOT EXISTS visuals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    question_id UUID REFERENCES questions(id) ON DELETE SET NULL,
    visual_key VARCHAR(50),  -- e.g., V1, v_q10_graph
    visual_type VARCHAR(50),  -- graph, diagram, image, chart, table
    latex_code TEXT,
    json_representation JSONB,
    description TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_visuals_concept_id ON visuals(concept_id);
CREATE INDEX IF NOT EXISTS idx_visuals_question_id ON visuals(question_id);
CREATE INDEX IF NOT EXISTS idx_visuals_type ON visuals(visual_type);
CREATE INDEX IF NOT EXISTS idx_visuals_key ON visuals(visual_key);
CREATE INDEX IF NOT EXISTS idx_visuals_metadata ON visuals USING GIN(metadata);

-- Add comments for documentation
COMMENT ON TABLE visuals IS 'Visual elements (graphs, diagrams, images) associated with concepts or questions';
COMMENT ON COLUMN visuals.visual_key IS 'Unique identifier for the visual within a document (e.g., V1, v_q10_graph)';
COMMENT ON COLUMN visuals.visual_type IS 'Type of visual: graph, diagram, image, chart, table';
COMMENT ON COLUMN visuals.latex_code IS 'LaTeX code for rendering the visual (if applicable)';
COMMENT ON COLUMN visuals.json_representation IS 'Structured JSON representation of the visual data';
COMMENT ON COLUMN visuals.description IS 'Textual description of the visual for semantic search';
