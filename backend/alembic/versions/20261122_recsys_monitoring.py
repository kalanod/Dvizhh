import sqlalchemy as sa

from alembic import op

revision = "20261122_recsys_monitoring"
down_revision = "20261121_discovery_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("discovery_pages", sa.Column("served_at", sa.DateTime(timezone=True)))
    op.alter_column("discovery_pages", "served_at", server_default=sa.func.clock_timestamp())
    op.create_index(op.f("ix_discovery_pages_served_at"), "discovery_pages", ["served_at"])
    impression = "type = 'IMPRESSION' AND session_id IS NOT NULL AND request_id IS NOT NULL"
    op.create_index(
        "ix_event_interactions_recsys_impression_received", "event_interactions", ["received_at"],
        postgresql_where=sa.text(impression),
    )
    op.execute(f"""
        CREATE VIEW public.recsys_attributed_impressions AS
        SELECT user_id::text, session_id::text, request_id::text, event_id::text AS item_id,
               occurrence_id::text, received_at
        FROM public.event_interactions WHERE {impression}
    """)


def downgrade() -> None:
    op.execute("DROP VIEW public.recsys_attributed_impressions")
    op.drop_index(
        "ix_event_interactions_recsys_impression_received", table_name="event_interactions",
    )
    op.drop_index(op.f("ix_discovery_pages_served_at"), table_name="discovery_pages")
    op.drop_column("discovery_pages", "served_at")
