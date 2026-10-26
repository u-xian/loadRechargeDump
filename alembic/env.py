"""
Alembic environment.

The connection URL is NOT read from alembic.ini; it is built from the .env
file by db.get_url() so that alembic, loadingFile.py and create_database.py
always point at the same database / DBMS.

Usage:
    alembic upgrade head            # create / upgrade the schema
    alembic downgrade base          # drop everything again
    alembic upgrade head --sql      # print the DDL for the configured DBMS
                                    # without touching the database
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# make "db" importable when alembic is launched from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_url, get_engine  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations are hand-written (no ORM models) -> no autogenerate metadata.
target_metadata = None


def run_migrations_offline() -> None:
    """Emit the SQL script instead of executing it (alembic ... --sql)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against the configured database."""
    connectable = get_engine(poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
