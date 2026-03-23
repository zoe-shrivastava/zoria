-- Migration 019: Allow 'failed' status on tests table
-- Background test generation sets status to 'failed' when question generation fails;
-- the original constraint only allowed draft, active, completed, expired.

-- Drop existing check constraint (name from 012: inline CHECK creates tests_status_check)
ALTER TABLE tests DROP CONSTRAINT IF EXISTS tests_status_check;

-- Re-add constraint including 'failed'
ALTER TABLE tests ADD CONSTRAINT tests_status_check
  CHECK (status IN ('draft', 'active', 'completed', 'expired', 'failed'));

COMMENT ON COLUMN tests.status IS 'Test status: draft, active, completed, expired, failed (generation error)';
