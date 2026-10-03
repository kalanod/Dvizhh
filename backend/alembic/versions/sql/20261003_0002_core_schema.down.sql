ALTER TABLE organizations DROP CONSTRAINT fk_organizations_avatar_media_id_media_assets;

ALTER TABLE profiles DROP CONSTRAINT fk_profiles_avatar_media_id_media_assets;


DROP TABLE story_items;


DROP TABLE participation_status_history;


DROP TABLE event_stories;


DROP TABLE event_interactions;


DROP TABLE event_invitations;


DROP TABLE event_participations;


DROP TABLE event_occurrences;


DROP TABLE event_media;


DROP TABLE external_event_links;


DROP TABLE recurrence_rules;


DROP TABLE event_topics;


DROP TABLE event_managers;


DROP TABLE event_dismissals;


DROP TABLE event_favorites;


DROP TABLE organization_members;


DROP TABLE events;


DROP TABLE media_assets;


DROP TABLE organizations;


DROP TABLE friendships;


DROP TABLE profiles;


DROP TABLE external_sources;


DROP TABLE locations;


DROP TABLE topics;

DROP TYPE participation_status;

DROP TYPE invitation_status;

DROP TYPE event_origin;

DROP TYPE event_status;

DROP TYPE event_visibility;

DROP TYPE event_join_policy;

DROP TYPE event_format;

DROP TYPE event_price_type;

DROP TYPE event_manager_role;

DROP TYPE occurrence_status;

DROP TYPE profile_status;

DROP TYPE friendship_status;

DROP TYPE organization_role;

DROP TYPE interaction_type;

DROP TYPE media_status;

DROP TYPE event_media_role;

DROP TYPE story_status;
