-- Create default admin user
-- Default credentials: admin@zoria.com / Admin123!
-- IMPORTANT: Change password and set up MFA after first login!

DO $$
DECLARE
    admin_id UUID;
    admin_password_hash TEXT;
BEGIN
    -- Check if admin already exists
    SELECT id INTO admin_id FROM parents WHERE email = 'admin@zoria.com';
    
    IF admin_id IS NULL THEN
        -- bcrypt hash for 'Admin123!' (generated with bcrypt.gensalt())
        admin_password_hash := '$2b$12$DlTdZ9xwDMQKfBM73zn97e8sDyzpucnVFjBBCaD7FggqLebdpKiQm';
        
        -- Create admin user
        -- MFA secret will be generated on first login attempt
        INSERT INTO parents (id, email, password_hash, role, mfa_secret, totp_enabled, created_at)
        VALUES (
            gen_random_uuid(),
            'admin@zoria.com',
            admin_password_hash,
            'admin',
            NULL, -- MFA secret will be generated on first login
            FALSE,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (email) DO NOTHING;
        
        RAISE NOTICE 'Default admin user created: admin@zoria.com';
        RAISE NOTICE 'Default password: Admin123!';
        RAISE NOTICE 'IMPORTANT: Change password and set up MFA after first login!';
    ELSE
        RAISE NOTICE 'Admin user already exists, skipping creation.';
    END IF;
END $$;
