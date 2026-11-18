from alembic import op

revision = "20261123_recsys_encoder_items"
down_revision = "20261122_recsys_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW public.recsys_encoder_items AS
        SELECT e.id AS item_id, e.title, e.description,
               ARRAY(SELECT t.tag_id FROM public.event_tags AS t
                     WHERE t.event_id = e.id ORDER BY t.tag_id) AS topic_ids
        FROM public.events AS e
        WHERE e.deleted_at IS NULL AND e.visibility = 'PUBLIC'
          AND e.status IN ('PUBLISHED', 'COMPLETED', 'ARCHIVED')
    """)


def downgrade() -> None:
    op.execute("DROP VIEW public.recsys_encoder_items")
