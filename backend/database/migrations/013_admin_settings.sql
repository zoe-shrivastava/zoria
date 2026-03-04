-- Migration 013: Admin settings key-value table
-- Stores small JSON configuration blobs, e.g. timestamp display settings for admin UI.

CREATE TABLE IF NOT EXISTS admin_settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

COMMENT ON TABLE admin_settings IS 'Key-value store for admin-configurable settings (JSON blobs).';
COMMENT ON COLUMN admin_settings.key IS 'Settings key (e.g., timestamp_settings).';
COMMENT ON COLUMN admin_settings.value IS 'Settings value stored as JSONB.';

