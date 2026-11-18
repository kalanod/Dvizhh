from alembic import op

revision = "20261124_recsys_participation"
down_revision = "20261121_discovery_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE VIEW public.recsys_participation_history AS
        SELECT p.user_id, p.occurrence_id, h.to_status::text AS status,
               h.changed_at, h.id AS change_id
        FROM public.event_participations AS p
        JOIN public.participation_status_history AS h ON h.participation_id = p.id
    """)


def downgrade() -> None:
    op.execute("DROP VIEW public.recsys_participation_history")
