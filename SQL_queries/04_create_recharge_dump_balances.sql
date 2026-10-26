-- =============================================================================
-- One row per bracket entry of the old BALANCES_INFO column, e.g.
--   [1~18768~5000~20261207233656][48~2730~0~20261115120921][49~875~22]...
-- Format: [balance_id ~ amount ~ delta ~ expiry_date(optional, yyyymmddhh24miss)]
-- Run AFTER 03_enable_explicit_recharge_id.sql
-- =============================================================================
CREATE TABLE IF NOT EXISTS recharge_dump_balances (
    balance_row_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recharge_id     INTEGER       NOT NULL,
    balance_id      INTEGER       NOT NULL,
    balance_amount  NUMERIC(18,2) NOT NULL,
    balance_delta   NUMERIC(18,2) NOT NULL,
    expiry_date     TIMESTAMP     NULL,

    CONSTRAINT fk_recharge_dump_balances_recharge
        FOREIGN KEY (recharge_id) REFERENCES recharge_dump_raw (recharge_id)
        ON DELETE CASCADE,

    -- A given recharge row cannot have the same balance bucket twice.
    CONSTRAINT ux_recharge_dump_balances_recharge_balance
        UNIQUE (recharge_id, balance_id)
);

CREATE INDEX IF NOT EXISTS ix_recharge_dump_balances_recharge_id
    ON recharge_dump_balances (recharge_id);

COMMENT ON TABLE  recharge_dump_balances                IS 'Exploded BALANCES_INFO entries from recharge_dump_raw, one row per bracket';
COMMENT ON COLUMN recharge_dump_balances.recharge_id    IS 'FK -> recharge_dump_raw.recharge_id';
COMMENT ON COLUMN recharge_dump_balances.balance_id      IS 'Balance bucket identifier (the first "~"-field of each bracket)';
COMMENT ON COLUMN recharge_dump_balances.balance_amount  IS 'Resulting balance amount';
COMMENT ON COLUMN recharge_dump_balances.balance_delta   IS 'Balance change applied (can be negative)';
COMMENT ON COLUMN recharge_dump_balances.expiry_date     IS 'Expiry timestamp of this balance bucket, if present in the source bracket';
