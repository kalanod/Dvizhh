import sqlalchemy as sa

from alembic import op

revision = "20261120_recsys_feedback"
down_revision = "20261119_invite_no_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("event_interactions", sa.Column("interaction_id", sa.Uuid()))
    op.add_column("event_interactions", sa.Column("received_at", sa.DateTime(timezone=True)))
    op.alter_column("event_interactions", "received_at", server_default=sa.func.now())
    op.create_unique_constraint(
        "uq_event_interactions_interaction_id", "event_interactions", ["interaction_id"]
    )
    for table in ("event_participations", "participation_status_history"):
        op.add_column(table, sa.Column("origin_interaction_id", sa.Uuid()))
        op.create_foreign_key(
            op.f(f"fk_{table}_origin_interaction_id_event_interactions"),
            table,
            "event_interactions",
            ["origin_interaction_id"],
            ["interaction_id"],
            ondelete="SET NULL",
        )
        op.create_index(op.f(f"ix_{table}_origin_interaction_id"), table, ["origin_interaction_id"])

    op.execute("""
        CREATE VIEW public.recsys_interactions AS
        SELECT user_id, event_id AS item_id, occurrence_id, type::text AS event_type,
               occurred_at, received_at, interaction_id, session_id, request_id
        FROM public.event_interactions
    """)
    op.execute("""
        CREATE VIEW public.recsys_confirmed_registrations AS
        SELECT p.user_id, o.event_id AS item_id, p.occurrence_id,
               h.changed_at AS confirmed_at, h.origin_interaction_id
        FROM public.participation_status_history AS h
        JOIN public.event_participations AS p ON p.id = h.participation_id
        JOIN public.event_occurrences AS o ON o.id = p.occurrence_id
        WHERE h.to_status = 'GOING' AND h.from_status IS DISTINCT FROM 'GOING'
    """)
    op.execute("""
        CREATE VIEW public.recsys_dismissals AS
        SELECT user_id, event_id AS item_id FROM public.event_dismissals
    """)
    op.execute("""
        CREATE VIEW public.recsys_catalog AS
        SELECT e.id AS item_id, o.id AS occurrence_id, e.title, e.description, e.search_document,
               e.published_at, e.created_at,
               GREATEST(e.updated_at, o.updated_at, l.updated_at) AS source_updated_at,
               o.starts_at, o.ends_at, o.timezone, o.is_all_day,
               COALESCE(o.capacity_override, e.capacity) AS capacity,
               (SELECT count(*) FROM public.event_participations AS p
                WHERE p.occurrence_id = o.id AND p.status = 'GOING') AS participants_count,
               e.price_type::text AS price_type, e.format::text AS format,
               e.join_policy::text AS join_policy, l.city,
               l.latitude::double precision AS latitude, l.longitude::double precision AS longitude,
               ARRAY(SELECT t.tag_id FROM public.event_tags AS t
                     WHERE t.event_id = e.id ORDER BY t.tag_id) AS topic_ids
        FROM public.events AS e
        JOIN public.event_occurrences AS o ON o.event_id = e.id
        LEFT JOIN public.locations AS l ON l.id = e.location_id
        WHERE e.deleted_at IS NULL AND e.status = 'PUBLISHED' AND e.visibility = 'PUBLIC'
          AND o.status = 'SCHEDULED'
    """)


def downgrade() -> None:
    for view in ("recsys_catalog", "recsys_dismissals", "recsys_confirmed_registrations",
                 "recsys_interactions"):
        op.execute(f"DROP VIEW public.{view}")
    for table in ("participation_status_history", "event_participations"):
        op.drop_index(op.f(f"ix_{table}_origin_interaction_id"), table_name=table)
        op.drop_constraint(
            op.f(f"fk_{table}_origin_interaction_id_event_interactions"), table, type_="foreignkey"
        )
        op.drop_column(table, "origin_interaction_id")
    op.drop_constraint(
        "uq_event_interactions_interaction_id", "event_interactions", type_="unique"
    )
    op.drop_column("event_interactions", "received_at")
    op.drop_column("event_interactions", "interaction_id")
