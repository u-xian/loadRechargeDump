import os
import re
import csv
from pathlib import Path
from io import StringIO

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

db_table = os.getenv('DB_TABLE')                                       # e.g. recharge_dump_raw
db_table_pk = os.getenv('DB_TABLE_PK', 'recharge_id')                  # primary key of db_table
log_table = os.getenv('DB_LOG_TABLE', 'recharge_dump_load_log')        # load log table
balances_table = os.getenv('DB_BALANCES_TABLE', 'recharge_dump_balances')  # exploded balances_info

csv_directory = os.path.join(BASE_DIR, os.getenv('DIR_DUMPS'))

# Columns that must be kept as text (leading zeros / 16-digit numbers would be
# mangled if pandas inferred them as float).
STRING_COLUMNS = {
    'CARD_NUMBER': str,
    'SERIAL_NUMBER': str,
    'BATCH_NUMBER': str,
}

# BALANCES_INFO format: "[1~18768~5000~20261207233656][48~2730~0][...]..."
#   bracket = balance_id ~ amount ~ delta ~ expiry_date(optional, yyyymmddhh24miss)
BALANCE_BRACKET_RE = re.compile(r'\[([^\]]*)\]')

STATUS_SUCCESS = 'LOAD SUCCESSFUL'
STATUS_FAILED = 'LOAD FAILED'

connection_url = URL.create(
    "postgresql+psycopg2",
    username=os.getenv("DB_USERNAME"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 5432)),
    database=os.getenv("DB_NAME"),
)

# Create a database engine
db = create_engine(connection_url)


def psql_insert_copy(table, conn, keys, data_iter):
    """pandas.to_sql 'method' that uses PostgreSQL COPY for fast bulk insert."""
    dbapi_conn = conn.connection
    with dbapi_conn.cursor() as cur:
        buf = StringIO()
        csv.writer(buf).writerows(data_iter)
        buf.seek(0)
        columns = ', '.join(f'"{k}"' for k in keys)
        table_name = f'{table.schema}.{table.name}' if table.schema else table.name
        cur.copy_expert(f'COPY {table_name} ({columns}) FROM STDIN WITH CSV', buf)


def already_loaded(file_name):
    """True if this file already has a LOAD SUCCESSFUL entry in the log table."""
    sql = text(f"""
        SELECT 1 FROM {log_table}
        WHERE file_name = :file_name AND status = :status
        LIMIT 1
    """)
    with db.connect() as conn:
        row = conn.execute(sql, {'file_name': file_name, 'status': STATUS_SUCCESS}).first()
    return row is not None


def log_failure(file_name, total_records, error):
    """Write a LOAD FAILED row to the log table (own transaction)."""
    sql = text(f"""
        INSERT INTO {log_table} (file_name, total_records, status, error_message)
        VALUES (:file_name, :total_records, :status, :error_message)
    """)
    with db.begin() as conn:
        conn.execute(sql, {
            'file_name': file_name,
            'total_records': total_records,
            'status': STATUS_FAILED,
            'error_message': str(error)[:4000],
        })


def explode_balances_info(recharge_ids, balances_info_series):
    """
    Turn the packed BALANCES_INFO column into a tidy DataFrame:
    one row per bracket, linked back to recharge_dump_raw via recharge_id.
    """
    records = []
    for recharge_id, packed in zip(recharge_ids, balances_info_series):
        if pd.isna(packed):
            continue
        for bracket in BALANCE_BRACKET_RE.findall(packed):
            parts = bracket.split('~')
            balance_id = parts[0]
            amount = parts[1]
            delta = parts[2]
            expiry_raw = parts[3] if len(parts) > 3 else None
            records.append((recharge_id, balance_id, amount, delta, expiry_raw))

    balances_df = pd.DataFrame(
        records,
        columns=['recharge_id', 'balance_id', 'balance_amount', 'balance_delta', 'expiry_date'],
    )
    if not balances_df.empty:
        balances_df['expiry_date'] = pd.to_datetime(
            balances_df['expiry_date'], format='%Y%m%d%H%M%S', errors='coerce'
        )
    return balances_df


def get_pk_sequence(conn, table, column):
    """Resolve the sequence backing an identity/serial primary key column."""
    seq = conn.execute(
        text("SELECT pg_get_serial_sequence(:table, :column)"),
        {'table': table, 'column': column},
    ).scalar_one_or_none()
    if not seq:
        raise RuntimeError(
            f"Could not resolve the identity sequence for {table}.{column}. "
            f"Has SQL_queries/03_enable_explicit_recharge_id.sql been applied?"
        )
    return seq


def load_file(file_name):
    """
    Load one CSV into db_table / balances_table. The log row and the data rows
    are written in a single transaction: either everything is committed
    (LOAD SUCCESSFUL) or nothing is, and a separate LOAD FAILED row is written.
    """
    file_path = os.path.join(csv_directory, file_name)
    total_records = 0

    try:
        # Read the CSV file into a pandas DataFrame
        df = pd.read_csv(file_path, dtype=STRING_COLUMNS)
        df.columns = df.columns.str.strip().str.lower()
        total_records = len(df)

        with db.begin() as conn:
            # 1. create the log row and get its id
            log_id = conn.execute(
                text(f"""
                    INSERT INTO {log_table} (file_name, total_records, status)
                    VALUES (:file_name, :total_records, :status)
                    RETURNING log_id
                """),
                {'file_name': file_name, 'total_records': total_records, 'status': STATUS_SUCCESS},
            ).scalar_one()

            # 2. reserve one recharge_dump_raw.recharge_id per row up-front so
            #    the same ids can be used to link the exploded balances rows
            #    below (requires recharge_id to be GENERATED BY DEFAULT, see
            #    sql/03_enable_explicit_recharge_id.sql).
            pk_sequence = get_pk_sequence(conn, db_table, db_table_pk)
            recharge_ids = conn.execute(
                text(f"SELECT nextval('{pk_sequence}') FROM generate_series(1, :n)"),
                {'n': total_records},
            ).scalars().all()
            df[db_table_pk] = recharge_ids
            df['file_id'] = log_id

            # 3. split balances_info out into its own tidy frame, then drop it
            #    from the row that goes into recharge_dump_raw.
            balances_df = explode_balances_info(df[db_table_pk], df['balances_info'])
            df = df.drop(columns=['balances_info'])

            # 4. bulk-load both tables (same transaction)
            df.to_sql(db_table, con=conn, if_exists='append', index=False,
                      chunksize=1000, method=psql_insert_copy)
            if not balances_df.empty:
                balances_df.to_sql(balances_table, con=conn, if_exists='append', index=False,
                                    chunksize=1000, method=psql_insert_copy)

        print(f"[OK]      {file_name}: {total_records} rows loaded "
              f"({len(balances_df)} balance entries, log_id={log_id})")
        return True

    except Exception as exc:
        # transaction above has been rolled back -> no partial data, no log row
        log_failure(file_name, total_records, exc)
        print(f"[FAILED]  {file_name}: {exc}")
        return False


if __name__ == '__main__':
    # Get a list of CSV files in the specified directory
    csv_files = sorted(f for f in os.listdir(csv_directory) if f.lower().endswith('.csv'))

    if not csv_files:
        print(f"No CSV files found in {csv_directory}")

    for file in csv_files:
        if already_loaded(file):
            print(f"[SKIPPED] {file}: already loaded successfully")
            continue
        load_file(file)
