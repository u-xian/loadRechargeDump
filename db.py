"""
Single place where the database connection is configured.

Used by loadingFile.py, create_database.py and alembic/env.py so that all of
them connect to the same database with the same settings.

The DBMS is selected with DB_DRIVER (SQLAlchemy "dialect+driver" string), e.g.

    DB_DRIVER=postgresql+psycopg2      (pip install psycopg2-binary)
    DB_DRIVER=oracle+oracledb          (pip install oracledb)
    DB_DRIVER=mssql+pyodbc             (pip install pyodbc + ODBC Driver 17/18)
    DB_DRIVER=mysql+pymysql            (pip install pymysql)
    DB_DRIVER=sqlite                   (built-in; DB_NAME is the file path)
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')


def get_url(database=None):
    """
    Build the SQLAlchemy URL from the .env file.

    `database` overrides DB_NAME - used by create_database.py to connect to the
    server's maintenance database (postgres / master / mysql) before the target
    database exists.
    """
    driver = os.getenv('DB_DRIVER', 'postgresql+psycopg2')
    db_name = database if database is not None else os.getenv('DB_NAME')

    if driver.startswith('sqlite'):
        # sqlite:///relative/path.db  or  sqlite:////absolute/path.db
        return make_url(f'sqlite:///{db_name}')

    query = {}
    if driver.startswith('mssql+pyodbc'):
        query['driver'] = os.getenv('DB_ODBC_DRIVER', 'ODBC Driver 18 for SQL Server')
        query['TrustServerCertificate'] = os.getenv('DB_TRUST_CERT', 'yes')

    return URL.create(
        driver,
        username=os.getenv('DB_USERNAME'),
        password=os.getenv('DB_PASSWORD'),
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT')) if os.getenv('DB_PORT') else None,
        database=db_name,
        query=query,
    )


def get_engine(database=None, **kwargs):
    url = get_url(database)
    if url.drivername.startswith('mssql+pyodbc'):
        kwargs.setdefault('fast_executemany', True)   # big speed-up for bulk inserts
    return create_engine(url, **kwargs)
