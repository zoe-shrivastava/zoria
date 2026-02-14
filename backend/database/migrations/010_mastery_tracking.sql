-- Migration 010: Create mastery tracking table
-- Tracks student progress and mastery scores for each concept

CREATE TABLE IF NOT EXISTS student_concept_mastery (
    student_id UUID REFERENCES children(id) ON DELETE CASCADE,
    concept_id UUID REFERENCES concepts(id) ON DELETE CASCADE,
    mastery_score DECIMAL(5,2) DEFAULT 0.0 CHECK (mastery_score >= 0 AND mastery_score <= 100),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, concept_id)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_mastery_student ON student_concept_mastery(student_id);
CREATE INDEX IF NOT EXISTS idx_mastery_concept ON student_concept_mastery(concept_id);
CREATE INDEX IF NOT EXISTS idx_mastery_score ON student_concept_mastery(mastery_score);
CREATE INDEX IF NOT EXISTS idx_mastery_last_updated ON student_concept_mastery(last_updated);

-- Create composite index for common queries (student + score range)
CREATE INDEX IF NOT EXISTS idx_mastery_student_score ON student_concept_mastery(student_id, mastery_score);

-- Add trigger to update last_updated timestamp
CREATE TRIGGER update_mastery_last_updated 
    BEFORE UPDATE ON student_concept_mastery
    FOR EACH ROW 
    WHEN (OLD.mastery_score IS DISTINCT FROM NEW.mastery_score)
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE student_concept_mastery IS 'Tracks student mastery scores for each concept (0-100 scale)';
COMMENT ON COLUMN student_concept_mastery.mastery_score IS 'Mastery score from 0.0 to 100.0, updated using exponential moving average';
COMMENT ON COLUMN student_concept_mastery.last_updated IS 'Timestamp of last mastery score update';

-- Helper function to update mastery score using exponential moving average
-- Formula: new_score = 0.7 * old_score + 0.3 * recent_performance
CREATE OR REPLACE FUNCTION update_mastery_score(
    p_student_id UUID,
    p_concept_id UUID,
    p_recent_performance DECIMAL
) RETURNS DECIMAL AS $$
DECLARE
    v_old_score DECIMAL;
    v_new_score DECIMAL;
BEGIN
    -- Get current mastery score (default to 0 if doesn't exist)
    SELECT COALESCE(mastery_score, 0.0) INTO v_old_score
    FROM student_concept_mastery
    WHERE student_id = p_student_id AND concept_id = p_concept_id;
    
    -- Calculate new score using exponential moving average
    -- Weight: 0.7 for old score, 0.3 for recent performance
    v_new_score := 0.7 * v_old_score + 0.3 * p_recent_performance;
    
    -- Ensure score is within bounds
    IF v_new_score > 100 THEN
        v_new_score := 100;
    ELSIF v_new_score < 0 THEN
        v_new_score := 0;
    END IF;
    
    -- Insert or update mastery score
    INSERT INTO student_concept_mastery (student_id, concept_id, mastery_score, last_updated)
    VALUES (p_student_id, p_concept_id, v_new_score, CURRENT_TIMESTAMP)
    ON CONFLICT (student_id, concept_id) 
    DO UPDATE SET 
        mastery_score = v_new_score,
        last_updated = CURRENT_TIMESTAMP;
    
    RETURN v_new_score;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_mastery_score IS 'Updates mastery score using exponential moving average (0.7 * old + 0.3 * recent)';
