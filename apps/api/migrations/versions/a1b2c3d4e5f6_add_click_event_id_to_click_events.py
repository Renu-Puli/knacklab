"""add click_event_id to click_events

Revision ID: a1b2c3d4e5f6
Revises: 994a8a4b27d0
Create Date: 2026-11-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '994a8a4b27d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('click_events', sa.Column('click_event_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_click_events_click_event_id'), 'click_events', ['click_event_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_click_events_click_event_id'), table_name='click_events')
    op.drop_column('click_events', 'click_event_id')
