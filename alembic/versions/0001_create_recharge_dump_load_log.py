"""create recharge_dump_load_log

One row per dump-file load attempt. log_id is referenced by
recharge_dump_raw.file_id (see 0002).

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

# BIGINT everywhere; SQLite only auto-increments INTEGER PRIMARY KEY
ID_TYPE = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')

STATUS_SUCCESS = 'LOAD SUCCESSFUL'
STATUS_FAILED = 'LOAD FAILED'


def upgrade() -> None:
    op.create_table(
        'recharge_dump_load_log',
        sa.Column('log_id', ID_TYPE, sa.Identity(start=1), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('total_records', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('loaded_date', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('log_id', name='pk_recharge_dump_load_log'),
        sa.CheckConstraint(
            f"status IN ('{STATUS_SUCCESS}', '{STATUS_FAILED}')",
            name='ck_load_log_status',
        ),
    )
    # NOTE: "a file can only be loaded successfully once" used to be a partial
    # unique index (WHERE status = 'LOAD SUCCESSFUL'). Partial indexes are not
    # supported by every DBMS (e.g. Oracle), so that rule is enforced by the
    # loader instead (already_loaded() in loadingFile.py). A plain index keeps
    # that lookup fast.
    op.create_index('ix_load_log_file_name', 'recharge_dump_load_log', ['file_name'])


def downgrade() -> None:
    op.drop_index('ix_load_log_file_name', table_name='recharge_dump_load_log')
    op.drop_table('recharge_dump_load_log')
