"""
Create the target database (DB_NAME from .env) if it does not exist yet.

Alembic only manages the *tables* inside a database; the database itself has
to exist before "alembic upgrade head" can run. This script does that step.

    python create_database.py

Behaviour per DBMS:
    PostgreSQL  connects to the maintenance db "postgres" and CREATE DATABASE
    SQL Server  connects to "master" and CREATE DATABASE
    MySQL       connects without a db and CREATE DATABASE
    SQLite      nothing to do - the file is created on first connection
    Oracle      an Oracle "database" is the whole instance; what corresponds to
                DB_NAME is a *schema/user*. Creating users needs DBA rights, so
                this script only prints the statement for the DBA to run.
"""
import sys

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from db import get_engine, get_url

# dialect -> (maintenance database to connect to, query that checks existence)
MAINTENANCE = {
    'postgresql': ('postgres', "SELECT 1 FROM pg_database WHERE datname = :name"),
    'mssql': ('master', "SELECT 1 FROM sys.databases WHERE name = :name"),
    'mysql': ('', "SELECT 1 FROM information_schema.schemata WHERE schema_name = :name"),
}


def main() -> int:
    url = get_url()
    dialect = url.get_backend_name()
    db_name = url.database

    if dialect == 'sqlite':
        print(f"SQLite: nothing to do, '{db_name}' is created on first connection.")
        return 0

    if dialect == 'oracle':
        print("Oracle: databases are not created per project. Ask the DBA to run:\n")
        print(f"    CREATE USER {url.username} IDENTIFIED BY <password>;")
        print(f"    GRANT CONNECT, RESOURCE, CREATE TABLE, CREATE SEQUENCE TO {url.username};")
        print(f"    ALTER USER {url.username} QUOTA UNLIMITED ON USERS;\n")
        print("then run: alembic upgrade head")
        return 0

    if dialect not in MAINTENANCE:
        print(f"Don't know how to create a database for dialect '{dialect}'. "
              f"Create '{db_name}' manually, then run: alembic upgrade head")
        return 1

    maintenance_db, exists_sql = MAINTENANCE[dialect]

    # CREATE DATABASE cannot run inside a transaction -> AUTOCOMMIT
    engine = get_engine(database=maintenance_db, isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as conn:
            exists = conn.execute(text(exists_sql), {'name': db_name}).first()
            if exists:
                print(f"Database '{db_name}' already exists.")
                return 0
            # identifiers cannot be bound as parameters -> quote via the dialect
            quoted = conn.dialect.identifier_preparer.quote(db_name)
            conn.execute(text(f"CREATE DATABASE {quoted}"))
            print(f"Database '{db_name}' created.")
            return 0
    except (OperationalError, ProgrammingError) as exc:
        print(f"Could not create database '{db_name}': {exc}")
        return 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    sys.exit(main())
