-- Migration 012: Create tests, test_questions, and test_responses tables
-- Enables test/quiz generation from knowledge graph concepts

-- Tests table: Represents a test/quiz session
CREATE TABLE IF NOT EXISTS tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_id UUID REFERENCES children(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES parents(id) ON DELETE SET NULL,
    concept_id UUID REFERENCES concepts(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'expired')),
    total_score DECIMAL(5,2),
    max_score DECIMAL(5,2),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    time_limit_minutes INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tests_child_id ON tests(child_id);
CREATE INDEX IF NOT EXISTS idx_tests_parent_id ON tests(parent_id);
CREATE INDEX IF NOT EXISTS idx_tests_concept_id ON tests(concept_id);
CREATE INDEX IF NOT EXISTS idx_tests_status ON tests(status);
CREATE INDEX IF NOT EXISTS idx_tests_child_status ON tests(child_id, status);
CREATE INDEX IF NOT EXISTS idx_tests_created_at ON tests(created_at DESC);

-- Test-Question junction table: Links questions to tests with ordering
CREATE TABLE IF NOT EXISTS test_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id UUID REFERENCES tests(id) ON DELETE CASCADE,
    question_id UUID REFERENCES questions(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    section_title VARCHAR(100),
    max_score DECIMAL(5,2) DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_test_questions_test ON test_questions(test_id);
CREATE INDEX IF NOT EXISTS idx_test_questions_question ON test_questions(question_id);
CREATE INDEX IF NOT EXISTS idx_test_questions_order ON test_questions(test_id, order_index);

-- Test responses table: Stores student answers for each question
CREATE TABLE IF NOT EXISTS test_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_id UUID REFERENCES tests(id) ON DELETE CASCADE,
    question_id UUID REFERENCES questions(id) ON DELETE CASCADE,
    answer TEXT,
    score DECIMAL(5,2),
    is_correct BOOLEAN,
    time_spent_seconds INTEGER,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(test_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_test_responses_test ON test_responses(test_id);
CREATE INDEX IF NOT EXISTS idx_test_responses_question ON test_responses(question_id);
CREATE INDEX IF NOT EXISTS idx_test_responses_submitted ON test_responses(submitted_at);

-- Add trigger to update tests.updated_at timestamp
CREATE TRIGGER update_tests_updated_at 
    BEFORE UPDATE ON tests
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE tests IS 'Test/quiz sessions linked to concepts from knowledge graph';
COMMENT ON COLUMN tests.status IS 'Test status: draft (created but not started), active (in progress), completed, expired';
COMMENT ON COLUMN tests.metadata IS 'Additional test metadata (sections, difficulty settings, etc.)';
COMMENT ON TABLE test_questions IS 'Junction table linking questions to tests with ordering and section grouping';
COMMENT ON COLUMN test_questions.order_index IS 'Order of question within test (0-based)';
COMMENT ON COLUMN test_questions.section_title IS 'Section name (e.g., "Multiple Choice", "Short Answer")';
COMMENT ON TABLE test_responses IS 'Student answers and scores for each question in a test';
COMMENT ON COLUMN test_responses.time_spent_seconds IS 'Time spent on this question in seconds';
