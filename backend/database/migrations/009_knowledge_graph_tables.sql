-- Migration 009: Create knowledge graph tables
-- Enables concept relationships, skill extraction, and prerequisite tracking

-- Skills table: Cognitive skills derived from questions
CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    cognitive_level VARCHAR(50),  -- remember, understand, apply, analyze, evaluate, create
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name);
CREATE INDEX IF NOT EXISTS idx_skills_cognitive_level ON skills(cognitive_level);

-- Concept relationships table: Links concepts with prerequisite/related relationships
CREATE TABLE IF NOT EXISTS concept_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    to_concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) CHECK (relationship_type IN (
        'prerequisite_of', 
        'related_to', 
        'builds_on',
        'requires'
    )),
    strength DECIMAL(3,2) DEFAULT 1.0 CHECK (strength >= 0 AND strength <= 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_concept_id, to_concept_id, relationship_type)
);

CREATE INDEX IF NOT EXISTS idx_concept_relationships_from ON concept_relationships(from_concept_id);
CREATE INDEX IF NOT EXISTS idx_concept_relationships_to ON concept_relationships(to_concept_id);
CREATE INDEX IF NOT EXISTS idx_concept_relationships_type ON concept_relationships(relationship_type);

-- Question-Skill relationships: Links questions to cognitive skills
CREATE TABLE IF NOT EXISTS question_skills (
    question_id UUID REFERENCES questions(id) ON DELETE CASCADE,
    skill_id UUID REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, skill_id)
);

CREATE INDEX IF NOT EXISTS idx_question_skills_question ON question_skills(question_id);
CREATE INDEX IF NOT EXISTS idx_question_skills_skill ON question_skills(skill_id);

-- Document-Concept links: Tracks which documents contain which concepts
-- (concepts table already has document_id, but this allows many-to-many if needed)
CREATE TABLE IF NOT EXISTS document_concepts (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, concept_id)
);

CREATE INDEX IF NOT EXISTS idx_document_concepts_document ON document_concepts(document_id);
CREATE INDEX IF NOT EXISTS idx_document_concepts_concept ON document_concepts(concept_id);

-- Add comments for documentation
COMMENT ON TABLE skills IS 'Cognitive skills extracted from questions (e.g., analyze, apply, evaluate)';
COMMENT ON TABLE concept_relationships IS 'Relationships between concepts (prerequisites, related concepts, etc.)';
COMMENT ON COLUMN concept_relationships.strength IS 'Strength of relationship (0.0 to 1.0)';
COMMENT ON COLUMN concept_relationships.relationship_type IS 'Type of relationship: prerequisite_of, related_to, builds_on, requires';
COMMENT ON TABLE question_skills IS 'Many-to-many relationship between questions and cognitive skills';
COMMENT ON TABLE document_concepts IS 'Many-to-many relationship between documents and concepts (for deduplicated concepts)';
