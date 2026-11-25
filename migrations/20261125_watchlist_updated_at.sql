-- Apply once to the configured PostgreSQL database after reviewing schema_audit output.
-- Additive and transactional: no table is dropped or recreated.
BEGIN;

ALTER TABLE watchlist
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE;

-- Preserve each existing row and use its original add time when available.
UPDATE watchlist
SET updated_at = COALESCE(added_at, CURRENT_TIMESTAMP)
WHERE updated_at IS NULL;

ALTER TABLE watchlist
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN updated_at SET NOT NULL;

-- The live schema has nullable status with no server default. Align it with
-- the existing SQLAlchemy model without changing non-null status values.
UPDATE watchlist SET status = 'PLANNED' WHERE status IS NULL;

ALTER TABLE watchlist
    ALTER COLUMN status SET DEFAULT 'PLANNED',
    ALTER COLUMN status SET NOT NULL;

COMMIT;
