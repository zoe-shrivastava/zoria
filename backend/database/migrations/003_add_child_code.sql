-- Add child_code column to children table
-- This will be a user-friendly unique identifier (e.g., "CHD123")

ALTER TABLE children 
ADD COLUMN IF NOT EXISTS child_code VARCHAR(20) UNIQUE;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_children_child_code ON children(child_code);

-- Generate child codes for existing children
-- Format: CHD + 6 random alphanumeric characters (uppercase letters and numbers, excluding confusing chars)
DO $$
DECLARE
    child_record RECORD;
    new_code VARCHAR(20);
    code_exists BOOLEAN;
    counter INTEGER;
    chars TEXT := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; -- Exclude 0/O, 1/I
    random_part TEXT;
    i INTEGER;
BEGIN
    FOR child_record IN SELECT id FROM children WHERE child_code IS NULL LOOP
        counter := 0;
        LOOP
            -- Generate 6 random characters from the allowed set
            random_part := '';
            FOR i IN 1..6 LOOP
                random_part := random_part || substr(chars, floor(random() * length(chars) + 1)::int, 1);
            END LOOP;
            
            new_code := 'CHD' || random_part;
            
            -- Check if code already exists
            SELECT EXISTS(SELECT 1 FROM children WHERE child_code = new_code) INTO code_exists;
            
            EXIT WHEN NOT code_exists OR counter > 10;
            counter := counter + 1;
        END LOOP;
        
        -- Update child with generated code
        UPDATE children SET child_code = new_code WHERE id = child_record.id;
    END LOOP;
END $$;
