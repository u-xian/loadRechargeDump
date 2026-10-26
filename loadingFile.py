"""
Load recharge dump CSV files into the database.

For every *.csv in DIR_DUMPS:
    0. check recharge_dump_load_log: if the file already has a LOAD SUCCESSFUL
       row it is NOT loaded again -> moved to DIR_ARCHIVE/duplicates/
    then, in one transaction:
    1. insert a row in recharge_dump_load_log            -> log_id
    2. insert the CSV rows in recharge_dump_raw          (file_id = log_id,
                                                          file_row_no = 1..n)
    3. read back (recharge_id, file_row_no) for that file_id
    4. explode BALANCES_INFO into recharge_dump_balances (recharge_id from 3.)
    5. on success the file is moved to DIR_ARCHIVE/
If anything fails the transaction is rolled back, a LOAD FAILED row is
written to the log table and the file stays in DIR_DUMPS to be fixed/re-run.

Schema is created with alembic (alembic upgrade head). The code only uses
generic SQL / SQLAlchemy Core, so it runs unchanged on PostgreSQL, Oracle,
SQL Server, MySQL, SQLite ... (select the DBMS with DB_DRIVER in .env).
"""
import os
import re
import csv
import shutil
from datetime import datetime
from io import StringIO

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import text

from db import BASE_DIR, get_engine

db_table = os.getenv('DB_TABLE', 'recharge_dump_raw')
log_table = os.getenv('DB_LOG_TABLE', 'recharge_dump_load_log')
balances_table = os.getenv('DB_BALANCES_TABLE', 'recharge_dump_balances')

csv_directory = os.path.join(BASE_DIR, os.getenv('DIR_DUMPS', 'dumps'))
archive_directory = os.path.join(BASE_DIR, os.getenv('DIR_ARCHIVE', 'archive'))
duplicates_directory = os.path.join(archive_directory, 'duplicates')

# Columns that must be kept as text (leading zeros / 16-digit numbers would be
# mangled if pandas inferred them as float).
STRING_COLUMNS = {
    'SUBSCRIBER_ID': str,
    'CARD_NUMBER': str,
    'SERIAL_NUMBER': str,
    'BATCH_NUMBER': str,
}

# BALANCES_INFO format: "[1~18768~5000~20261207233656][48~2730~0][...]..."
#   bracket = balance_id ~ amount ~ delta ~ expiry_date(optional, yyyymmddhh24miss)
BALANCE_BRACKET_RE = re.compile(r'\[([^\]]*)\]')

STATUS_SUCCESS = 'LOAD SUCCESSFUL'
STATUS_FAILED = 'LOAD FAILED'

db = get_engine()

# Minimal Core definition of the log table: lets SQLAlchemy fetch the
# generated log_id in the way each DBMS supports (RETURNING / OUTPUT /
# lastrowid / RETURNING INTO) instead of hand-written dialect SQL.
_metadata = sa.MetaData()
LOG_TABLE = sa.Table(
    log_table, _metadata,
    sa.Column('log_id', sa.BigInteger, primary_key=True),
    sa.Column('file_name', sa.String(255)),
    sa.Column('total_records', sa.Integer),
    sa.Column('status', sa.String(20)),
    sa.Column('error_message', sa.Text),
)


# --------------------------------------------------------------------------- #
# bulk insert
# --------------------------------------------------------------------------- #
def psql_insert_copy(table, conn, keys, data_iter):
    """PostgreSQL-only fast path: pandas.to_sql 'method' using COPY."""
    dbapi_conn = conn.connection
    with dbapi_conn.cursor() as cur:
        buf = StringIO()
        csv.writer(buf).writerows(data_iter)
        buf.seek(0)
        columns = ', '.join(f'"{k}"' for k in keys)
        table_name = f'{table.schema}.{table.name}' if table.schema else table.name
        cur.copy_expert(f'COPY {table_name} ({columns}) FROM STDIN WITH CSV', buf)


def bulk_insert(df, table_name, conn):
    """Append a DataFrame to a table using the fastest portable method."""
    if conn.dialect.name == 'postgresql':
        method = psql_insert_copy
    else:
        method = None          # standard executemany (fast_executemany on mssql)
    df.to_sql(table_name, con=conn, if_exists='append', index=False,
              chunksize=1000, method=method)


# --------------------------------------------------------------------------- #
# log table helpers
# --------------------------------------------------------------------------- #
def already_loaded(file_name):
    """True if this file already has a LOAD SUCCESSFUL entry in the log table."""
    sql = text(f"""
        SELECT 1 FROM {log_table}
        WHERE file_name = :file_name AND status = :status
    """)
    with db.connect() as conn:
        row = conn.execute(sql, {'file_name': file_name, 'status': STATUS_SUCCESS}).first()
    return row is not None


def insert_log_row(conn, file_name, total_records, status, error_message=None):
    """Insert a log row and return its generated log_id (portable)."""
    result = conn.execute(
        sa.insert(LOG_TABLE).values(
            file_name=file_name,
            total_records=total_records,
            status=status,
            error_message=error_message,
        )
    )
    return result.inserted_primary_key[0]


def log_failure(file_name, total_records, error):
    """Write a LOAD FAILED row to the log table (own transaction)."""
    with db.begin() as conn:
        insert_log_row(conn, file_name, total_records, STATUS_FAILED,
                       error_message=str(error)[:4000])


# --------------------------------------------------------------------------- #
# transformations
# --------------------------------------------------------------------------- #
def prepare_raw_frame(df, log_id):
    """Lower-case columns, typed dates, file_id / file_row_no, no balances_info."""
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()

    # Real datetime/date objects so every DB driver binds them correctly
    # (Oracle / SQL Server do not reliably cast strings to DATE/DATETIME).
    df['recharge_date_time'] = pd.to_datetime(df['recharge_date_time'])
    if 'filedate' in df.columns:
        df['filedate'] = pd.to_datetime(df['filedate']).dt.date

    df['file_id'] = log_id
    df['file_row_no'] = range(1, len(df) + 1)
    return df


def explode_balances_info(file_row_nos, balances_info_series):
    """
    Turn the packed BALANCES_INFO column into a tidy DataFrame:
    one row per bracket, keyed by file_row_no (mapped to recharge_id later).
    """
    records = []
    for row_no, packed in zip(file_row_nos, balances_info_series):
        if pd.isna(packed):
            continue
        for bracket in BALANCE_BRACKET_RE.findall(packed):
            parts = bracket.split('~')
            balance_id = parts[0]
            amount = parts[1]
            delta = parts[2]
            expiry_raw = parts[3] if len(parts) > 3 else None
            records.append((row_no, balance_id, amount, delta, expiry_raw))

    balances_df = pd.DataFrame(
        records,
        columns=['file_row_no', 'balance_id', 'balance_amount', 'balance_delta', 'expiry_date'],
    )
    if not balances_df.empty:
        balances_df['balance_id'] = balances_df['balance_id'].astype(int)
        balances_df['balance_amount'] = pd.to_numeric(balances_df['balance_amount'])
        balances_df['balance_delta'] = pd.to_numeric(balances_df['balance_delta'])
        balances_df['expiry_date'] = pd.to_datetime(
            balances_df['expiry_date'], format='%Y%m%d%H%M%S', errors='coerce'
        )
    return balances_df


def fetch_recharge_ids(conn, log_id):
    """{file_row_no: recharge_id} for every raw row of this file (portable)."""
    rows = conn.execute(
        text(f"SELECT recharge_id, file_row_no FROM {db_table} WHERE file_id = :file_id"),
        {'file_id': log_id},
    ).all()
    return {row_no: recharge_id for recharge_id, row_no in rows}


# --------------------------------------------------------------------------- #
# archiving
# --------------------------------------------------------------------------- #
def archive_file(file_name, target_directory):
    """
    Move dumps/<file_name> into target_directory. If a file with the same name
    is already there, a timestamp is appended so nothing is ever overwritten.
    Returns the final path.
    """
    os.makedirs(target_directory, exist_ok=True)
    src = os.path.join(csv_directory, file_name)
    dst = os.path.join(target_directory, file_name)
    if os.path.exists(dst):
        stem, ext = os.path.splitext(file_name)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dst = os.path.join(target_directory, f'{stem}_{stamp}{ext}')
    shutil.move(src, dst)
    return dst


# --------------------------------------------------------------------------- #
# main load
# --------------------------------------------------------------------------- #
def load_file(file_name):
    """
    Load one CSV into db_table / balances_table. The log row and the data rows
    are written in a single transaction: either everything is committed
    (LOAD SUCCESSFUL) or nothing is, and a separate LOAD FAILED row is written.
    """
    file_path = os.path.join(csv_directory, file_name)
    total_records = 0

    try:
        df = pd.read_csv(file_path, dtype=STRING_COLUMNS)
        total_records = len(df)

        with db.begin() as conn:
            # 1. log row -> log_id
            log_id = insert_log_row(conn, file_name, total_records, STATUS_SUCCESS)

            # 2. raw rows (balances_info is split off and not stored here)
            raw_df = prepare_raw_frame(df, log_id)
            balances_df = explode_balances_info(raw_df['file_row_no'], raw_df['balances_info'])
            raw_df = raw_df.drop(columns=['balances_info'])
            bulk_insert(raw_df, db_table, conn)

            # 3. recharge_id generated by the DB for each file_row_no
            id_map = fetch_recharge_ids(conn, log_id)

            # 4. balances rows, linked through recharge_id
            if not balances_df.empty:
                balances_df['recharge_id'] = balances_df['file_row_no'].map(id_map)
                balances_df = balances_df.drop(columns=['file_row_no'])
                bulk_insert(balances_df, balances_table, conn)

        print(f"[OK]      {file_name}: {total_records} rows loaded "
              f"({len(balances_df)} balance entries, log_id={log_id})")
        return True

    except Exception as exc:
        # transaction above has been rolled back -> no partial data, no log row
        log_failure(file_name, total_records, exc)
        first_line = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        print(f"[FAILED]  {file_name}: {first_line}")
        return False


def process_file(file_name):
    """
    Full lifecycle of one dump file:
      1. duplicate check against the log table
      2. load
      3. archive (success -> archive/, duplicate -> archive/duplicates/,
                  failure -> file is left in dumps/)
    """
    # 1. already loaded? -> never load twice
    if already_loaded(file_name):
        dst = archive_file(file_name, duplicates_directory)
        print(f"[SKIPPED] {file_name}: already loaded successfully "
              f"-> moved to {os.path.relpath(dst, BASE_DIR)}")
        return

    # 2. load
    loaded = load_file(file_name)

    # 3. archive only what was committed
    if loaded:
        dst = archive_file(file_name, archive_directory)
        print(f"[ARCHIVED] {file_name} -> {os.path.relpath(dst, BASE_DIR)}")
    else:
        print(f"[KEPT]    {file_name}: left in {os.path.relpath(csv_directory, BASE_DIR)}/ for correction")


if __name__ == '__main__':
    os.makedirs(csv_directory, exist_ok=True)
    csv_files = sorted(f for f in os.listdir(csv_directory) if f.lower().endswith('.csv'))

    if not csv_files:
        print(f"No CSV files found in {csv_directory}")

    for file in csv_files:
        process_file(file)
