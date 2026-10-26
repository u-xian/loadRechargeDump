# loadRechargeDump

Loads recharge dump CSV files into a relational database. The schema is
managed with **Alembic**, and both the migrations and the loader use only
generic SQL / SQLAlchemy Core, so the same code runs on PostgreSQL, Oracle,
SQL Server, MySQL and SQLite — the DBMS is selected in `.env`.

```
loadRechargeDump/
├── alembic.ini                 alembic config (URL comes from .env, not from here)
├── alembic/
│   ├── env.py                  builds the connection from db.py
│   └── versions/
│       ├── 0001_create_recharge_dump_load_log.py
│       ├── 0002_create_recharge_dump_raw.py
│       └── 0003_create_recharge_dump_balances.py
├── db.py                       single place that builds the SQLAlchemy URL / engine
├── create_database.py          creates the database itself (alembic only manages tables)
├── loadingFile.py              the loader
├── dumps/                      drop the *.csv files here
├── .env.example                copy to .env and edit
└── requirements.txt
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# + the driver for your DBMS (see requirements.txt): psycopg2-binary / oracledb / pyodbc / pymysql
```

## Create the database and the tables

```bash
python create_database.py      # 1. create the database if it does not exist
alembic upgrade head           # 2. create / upgrade all tables
```

| DBMS       | `DB_DRIVER`           | `create_database.py`                                                                                                    |
| ---------- | --------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| PostgreSQL | `postgresql+psycopg2` | connects to `postgres`, `CREATE DATABASE`                                                                               |
| SQL Server | `mssql+pyodbc`        | connects to `master`, `CREATE DATABASE`                                                                                 |
| MySQL      | `mysql+pymysql`       | `CREATE DATABASE`                                                                                                       |
| SQLite     | `sqlite`              | nothing to do (file is created automatically)                                                                           |
| Oracle     | `oracle+oracledb`     | prints the `CREATE USER`/`GRANT` for the DBA (an Oracle "database" is the instance; the project lives in a schema/user) |

Useful alembic commands:

```bash
alembic current                 # which revision is the DB at
alembic upgrade head --sql      # show the DDL for the configured DBMS, don't execute
alembic downgrade base          # drop all tables
alembic revision -m "..."       # add a new migration (hand-written, no autogenerate)
```

## Load files

```bash
python loadingFile.py
```

For every `*.csv` in `DIR_DUMPS` (one transaction per file):

1. insert a row in `recharge_dump_load_log` → `log_id`
2. insert the CSV rows in `recharge_dump_raw` (`file_id = log_id`, `file_row_no = 1..n`)
3. read back the DB-generated `recharge_id` for each `file_row_no`
4. explode `BALANCES_INFO` (`[balance_id~amount~delta~expiry]...`) into `recharge_dump_balances`

If anything fails, the transaction is rolled back (no partial data) and a
`LOAD FAILED` row with the error is written to the log. Files already marked
`LOAD SUCCESSFUL` are skipped on re-run.

## Schema

```
recharge_dump_load_log (log_id PK, file_name, total_records, status, error_message, loaded_date)
        │ 1
        │ file_id
        ▼ n
recharge_dump_raw (recharge_id PK, subscriber_id, recharge_date_time, ..., file_id FK, file_row_no)
        │ 1
        │ recharge_id
        ▼ n
recharge_dump_balances (balance_row_id PK, recharge_id FK, balance_id, balance_amount, balance_delta, expiry_date)
```

## Migrating an existing PostgreSQL database created with the old SQL scripts

The alembic schema is not byte-identical to the hand-written one
(`file_row_no` is new, `balances_info` is gone, constraint names are shorter).
Simplest path: export what you need, `DROP` the three old tables, then
`alembic upgrade head` and reload the CSV files.
