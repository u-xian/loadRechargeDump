-- =============================================================================
-- Run ONLY after 05_migrate_existing_balances_info.sql has been applied
-- (or if recharge_dump_raw is empty / newly created).
-- =============================================================================
ALTER TABLE recharge_dump_raw
    DROP COLUMN IF EXISTS balances_info;
