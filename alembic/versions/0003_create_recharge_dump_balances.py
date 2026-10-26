"""create recharge_dump_balances

One row per bracket of the CSV's BALANCES_INFO column, e.g.
    [1~18768~5000~20261207233656][48~2730~0~20261115120921][49~875~22]...
Format: [balance_id ~ amount ~ delta ~ expiry_date(optional, yyyymmddhh24miss)]

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

# BIGINT everywhere; SQLite only auto-increments INTEGER PRIMARY KEY
ID_TYPE = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def upgrade() -> None:
    op.create_table(
        'recharge_dump_balances',
        sa.Column('balance_row_id', ID_TYPE, sa.Identity(start=1), nullable=False),
        sa.Column('recharge_id', sa.BigInteger(), nullable=False),
        sa.Column('balance_id', sa.Integer(), nullable=False),
        sa.Column('balance_amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('balance_delta', sa.Numeric(18, 2), nullable=False),
        sa.Column('expiry_date', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('balance_row_id', name='pk_recharge_dump_balances'),
        sa.ForeignKeyConstraint(
            ['recharge_id'], ['recharge_dump_raw.recharge_id'],
            name='fk_balances_recharge_id',
            ondelete='CASCADE',
        ),
        # a given recharge row cannot have the same balance bucket twice
        sa.UniqueConstraint('recharge_id', 'balance_id', name='ux_balances_recharge_balance'),
    )
    op.create_index('ix_balances_recharge_id', 'recharge_dump_balances', ['recharge_id'])
    op.create_index('ix_balances_balance_id', 'recharge_dump_balances', ['balance_id'])


def downgrade() -> None:
    op.drop_index('ix_balances_balance_id', table_name='recharge_dump_balances')
    op.drop_index('ix_balances_recharge_id', table_name='recharge_dump_balances')
    op.drop_table('recharge_dump_balances')
