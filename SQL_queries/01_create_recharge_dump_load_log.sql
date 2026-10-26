-- =============================================================================
-- Load log table: one row per dump file load attempt.
-- log_id is referenced by recharge_dump_raw.file_id (see 02_*.sql)
-- =============================================================================
CREATE TABLE IF NOT EXISTS recharge_dump_load_log (
    log_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name       VARCHAR(255) NOT NULL,
    total_records   INTEGER      NOT NULL DEFAULT 0,
    status          VARCHAR(20)  NOT NULL
                    CONSTRAINT ck_recharge_dump_load_log_status
                    CHECK (status IN ('LOAD SUCCESSFUL', 'LOAD FAILED')),
    error_message   TEXT         NULL,          -- populated only when status = 'LOAD FAILED'
    loaded_date     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A given file may only be loaded successfully once.
-- (Failed attempts can repeat, so the index is partial.)
CREATE UNIQUE INDEX IF NOT EXISTS ux_recharge_dump_load_log_file_success
    ON recharge_dump_load_log (file_name)
    WHERE status = 'LOAD SUCCESSFUL';

COMMENT ON TABLE  recharge_dump_load_log               IS 'Audit log of recharge dump CSV files loaded into recharge_dump_raw';
COMMENT ON COLUMN recharge_dump_load_log.log_id        IS 'Surrogate key, referenced by recharge_dump_raw.file_id';
COMMENT ON COLUMN recharge_dump_load_log.file_name     IS 'Name of the CSV file loaded (e.g. RechargeDump_20261009.csv)';
COMMENT ON COLUMN recharge_dump_load_log.total_records IS 'Number of data rows in the file (excluding header)';
COMMENT ON COLUMN recharge_dump_load_log.status        IS 'LOAD SUCCESSFUL or LOAD FAILED';
COMMENT ON COLUMN recharge_dump_load_log.loaded_date   IS 'Timestamp of the load attempt';
