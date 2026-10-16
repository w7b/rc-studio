-- Existing databases kept the original CHECK despite CREATE TABLE IF NOT EXISTS.
-- Remove role checks before converting data, then install the current constraint.
DO $$
DECLARE role_check RECORD;
BEGIN
    FOR role_check IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'memberships'::regclass AND contype = 'c'
          AND conkey @> ARRAY[(SELECT attnum FROM pg_attribute
                              WHERE attrelid = 'memberships'::regclass AND attname = 'role')]
    LOOP
        EXECUTE format('ALTER TABLE memberships DROP CONSTRAINT %I', role_check.conname);
    END LOOP;
END $$;

UPDATE memberships SET role = CASE role
    WHEN 'owner' THEN 'OWNER' WHEN 'manager' THEN 'PAID' WHEN 'editor' THEN 'DEFAULT'
    ELSE role END;
UPDATE sessions SET role = CASE role
    WHEN 'owner' THEN 'OWNER' WHEN 'manager' THEN 'PAID' WHEN 'editor' THEN 'DEFAULT'
    ELSE role END;
UPDATE invites SET role = CASE role
    WHEN 'owner' THEN 'OWNER' WHEN 'manager' THEN 'PAID' WHEN 'editor' THEN 'DEFAULT'
    ELSE role END;

ALTER TABLE memberships ADD CONSTRAINT memberships_role_check
    CHECK (role IN ('DEFAULT', 'PAID', 'OWNER'));
