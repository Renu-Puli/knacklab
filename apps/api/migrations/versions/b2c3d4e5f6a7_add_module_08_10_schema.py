"""add is_active and title to links and create partitioning

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-23 03:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add is_active and title to links
    op.add_column('links', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('links', sa.Column('title', sa.String(length=255), nullable=True))
    
    # 2. Add composite indexes from Module 08
    op.create_index('ix_links_tenant_created', 'links', ['created_by', sa.text('created_at DESC'), sa.text('id DESC')])
    op.create_index('ix_click_events_link_clicked', 'click_events', ['link_id', sa.text('clicked_at DESC')])
    
    # 3. Create partitioned table for telemetry from Module 09
    op.execute("""
        CREATE TABLE IF NOT EXISTS click_events_partitioned (
            id SERIAL,
            click_event_id VARCHAR(64) NOT NULL,
            link_id INTEGER NOT NULL,
            clicked_at TIMESTAMP WITH TIME ZONE NOT NULL,
            user_agent VARCHAR,
            referrer VARCHAR,
            ip_hash VARCHAR(64),
            PRIMARY KEY (id, clicked_at)
        ) PARTITION BY RANGE (clicked_at);
        
        CREATE TABLE IF NOT EXISTS click_events_p2026_11 
        PARTITION OF click_events_partitioned
        FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00');
        
        CREATE TABLE IF NOT EXISTS click_events_p_default 
        PARTITION OF click_events_partitioned DEFAULT;
    """)


def downgrade() -> None:
    op.drop_index('ix_click_events_link_clicked', table_name='click_events')
    op.drop_index('ix_links_tenant_created', table_name='links')
    op.drop_column('links', 'title')
    op.drop_column('links', 'is_active')
    op.execute("DROP TABLE IF EXISTS click_events_partitioned CASCADE;")
