-- =============================================================================
-- Add file_id to recharge_dump_raw as a foreign key to recharge_dump_load_log.
-- Run AFTER 01_create_recharge_dump_load_log.sql
-- =============================================================================
ALTER TABLE recharge_dump_raw
    ADD COLUMN IF NOT EXISTS file_id BIGINT;

ALTER TABLE recharge_dump_raw
    DROP CONSTRAINT IF EXISTS fk_recharge_dump_raw_file_id;

ALTER TABLE recharge_dump_raw
    ADD CONSTRAINT fk_recharge_dump_raw_file_id
    FOREIGN KEY (file_id) REFERENCES recharge_dump_load_log (log_id);

-- Speeds up joins / "give me all rows from file X" / cascade checks
CREATE INDEX IF NOT EXISTS ix_recharge_dump_raw_file_id
    ON recharge_dump_raw (file_id);

COMMENT ON COLUMN recharge_dump_raw.file_id IS 'FK -> recharge_dump_load_log.log_id : the dump file this row came from';

-- Optional: once all pre-existing rows have a file_id (or the table is empty),
-- enforce it:
-- ALTER TABLE recharge_dump_raw ALTER COLUMN file_id SET NOT NULL;
