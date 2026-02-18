-- Migration 018: Child preferences for cultural/context flexibility
-- Adds optional columns to children for language, interaction tone, example preferences,
-- interests, sensitive topics to avoid, and prefer indirect guidance.
-- tests.metadata is already JSONB (012) - used for inferred_session_state (no schema change).

-- Preferred language (e.g. 'English', 'Hindi', 'Spanish') - can override frontend selection
ALTER TABLE children
ADD COLUMN IF NOT EXISTS preferred_language VARCHAR(50);

-- Interaction tone: playful, encouraging, direct, gentle
ALTER TABLE children
ADD COLUMN IF NOT EXISTS interaction_tone VARCHAR(50);

-- Example style: storytelling, step-by-step, factual
ALTER TABLE children
ADD COLUMN IF NOT EXISTS example_preferences VARCHAR(100);

-- Interests for examples (e.g. 'sports, animals, music')
ALTER TABLE children
ADD COLUMN IF NOT EXISTS interests TEXT;

-- Sensitive topics to avoid (free text, parent-configured)
ALTER TABLE children
ADD COLUMN IF NOT EXISTS sensitive_topics_to_avoid TEXT;

-- Prefer indirect guidance for emotional/sensitive topics
ALTER TABLE children
ADD COLUMN IF NOT EXISTS prefer_indirect_guidance BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN children.preferred_language IS 'Preferred language for study guides, tests, and chat (e.g. English, Hindi, Spanish)';
COMMENT ON COLUMN children.interaction_tone IS 'Tone of AI: playful, encouraging, direct, gentle';
COMMENT ON COLUMN children.example_preferences IS 'How to give examples: storytelling, step-by-step, factual';
COMMENT ON COLUMN children.interests IS 'Child interests for contextual examples (comma-separated or free text)';
COMMENT ON COLUMN children.sensitive_topics_to_avoid IS 'Topics to avoid in content (parent-configured)';
COMMENT ON COLUMN children.prefer_indirect_guidance IS 'Use indirect phrasing for emotional/sensitive topics';
