CREATE TYPE participation_status AS ENUM ('REQUESTED', 'GOING', 'REJECTED', 'CANCELLED');

CREATE TYPE invitation_status AS ENUM ('PENDING', 'ACCEPTED', 'DECLINED', 'REVOKED', 'EXPIRED');

CREATE TYPE event_origin AS ENUM ('USER', 'ORGANIZATION', 'EXTERNAL');

CREATE TYPE event_status AS ENUM ('DRAFT', 'PUBLISHED', 'CANCELLED', 'COMPLETED', 'ARCHIVED');

CREATE TYPE event_visibility AS ENUM ('PUBLIC', 'FRIENDS', 'UNLISTED', 'PRIVATE');

CREATE TYPE event_join_policy AS ENUM ('OPEN', 'REQUEST', 'INVITE_ONLY', 'EXTERNAL');

CREATE TYPE event_format AS ENUM ('OFFLINE', 'ONLINE', 'HYBRID');

CREATE TYPE event_price_type AS ENUM ('FREE', 'PAID');

CREATE TYPE event_manager_role AS ENUM ('OWNER', 'MANAGER');

CREATE TYPE occurrence_status AS ENUM ('SCHEDULED', 'CANCELLED', 'COMPLETED');

CREATE TYPE profile_status AS ENUM ('ACTIVE', 'SUSPENDED', 'DELETED');

CREATE TYPE friendship_status AS ENUM ('PENDING', 'ACCEPTED', 'DECLINED', 'REMOVED');

CREATE TYPE organization_role AS ENUM ('OWNER', 'ADMIN', 'EDITOR');

CREATE TYPE interaction_type AS ENUM ('IMPRESSION', 'OPEN', 'FAVORITE_ADD', 'FAVORITE_REMOVE', 'NOT_INTERESTED', 'JOIN_CLICK', 'REQUEST_SUBMITTED', 'REQUEST_ACCEPTED', 'REQUEST_REJECTED', 'PARTICIPATION_CANCELLED', 'EXTERNAL_LINK_CLICK');

CREATE TYPE media_status AS ENUM ('UPLOADING', 'READY', 'FAILED', 'DELETED');

CREATE TYPE event_media_role AS ENUM ('COVER', 'GALLERY');

CREATE TYPE story_status AS ENUM ('DRAFT', 'PUBLISHED', 'ARCHIVED');


CREATE TABLE topics (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	parent_id UUID,
	slug VARCHAR(80) NOT NULL,
	name VARCHAR(120) NOT NULL,
	description TEXT,
	is_active BOOLEAN DEFAULT true NOT NULL,
	sort_order INTEGER DEFAULT 0 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_topics PRIMARY KEY (id),
	CONSTRAINT fk_topics_parent_id_topics FOREIGN KEY(parent_id) REFERENCES topics (id) ON DELETE SET NULL,
	CONSTRAINT uq_topics_slug UNIQUE (slug)
)

;

CREATE INDEX ix_topics_active_sort_order ON topics (is_active, sort_order);

CREATE INDEX ix_topics_parent_sort_order ON topics (parent_id, sort_order);


CREATE TABLE locations (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	name VARCHAR(200),
	country_code VARCHAR(2),
	region VARCHAR(120),
	city VARCHAR(120),
	address_line TEXT,
	postal_code VARCHAR(20),
	latitude NUMERIC(9, 6) NOT NULL,
	longitude NUMERIC(9, 6) NOT NULL,
	external_place_id VARCHAR(255),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_locations PRIMARY KEY (id),
	CONSTRAINT ck_locations_latitude_range CHECK (latitude BETWEEN -90 AND 90),
	CONSTRAINT ck_locations_longitude_range CHECK (longitude BETWEEN -180 AND 180)
)

;

CREATE INDEX ix_locations_city_region ON locations (city, region);

CREATE INDEX ix_locations_external_place_id ON locations (external_place_id);


CREATE TABLE external_sources (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	code VARCHAR(80) NOT NULL,
	name VARCHAR(160) NOT NULL,
	base_url TEXT,
	is_active BOOLEAN DEFAULT true NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_external_sources PRIMARY KEY (id),
	CONSTRAINT uq_external_sources_code UNIQUE (code)
)

;


CREATE TABLE profiles (
	id UUID NOT NULL,
	username VARCHAR(50) NOT NULL,
	display_name VARCHAR(120) NOT NULL,
	bio TEXT,
	avatar_media_id UUID,
	city VARCHAR(120),
	latitude NUMERIC(9, 6),
	longitude NUMERIC(9, 6),
	status profile_status DEFAULT 'ACTIVE' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_profiles PRIMARY KEY (id),
	CONSTRAINT ck_profiles_latitude_range CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
	CONSTRAINT ck_profiles_longitude_range CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
	CONSTRAINT uq_profiles_username UNIQUE (username)
)

;

CREATE INDEX ix_profiles_status_created_at ON profiles (status, created_at);

CREATE INDEX ix_profiles_display_name ON profiles (display_name);


CREATE TABLE friendships (
	user_low_id UUID NOT NULL,
	user_high_id UUID NOT NULL,
	requested_by_user_id UUID NOT NULL,
	status friendship_status DEFAULT 'PENDING' NOT NULL,
	requested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	responded_at TIMESTAMP WITH TIME ZONE,
	removed_at TIMESTAMP WITH TIME ZONE,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_friendships PRIMARY KEY (user_low_id, user_high_id),
	CONSTRAINT ck_friendships_canonical_user_order CHECK (user_low_id < user_high_id),
	CONSTRAINT ck_friendships_requester_is_member CHECK (requested_by_user_id IN (user_low_id, user_high_id)),
	CONSTRAINT fk_friendships_user_low_id_profiles FOREIGN KEY(user_low_id) REFERENCES profiles (id) ON DELETE CASCADE,
	CONSTRAINT fk_friendships_user_high_id_profiles FOREIGN KEY(user_high_id) REFERENCES profiles (id) ON DELETE CASCADE,
	CONSTRAINT fk_friendships_requested_by_user_id_profiles FOREIGN KEY(requested_by_user_id) REFERENCES profiles (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_friendships_user_high_status ON friendships (user_high_id, status);

CREATE INDEX ix_friendships_status_updated_at ON friendships (status, updated_at);


CREATE TABLE organizations (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	slug VARCHAR(80) NOT NULL,
	name VARCHAR(160) NOT NULL,
	description TEXT,
	avatar_media_id UUID,
	website_url TEXT,
	is_verified BOOLEAN DEFAULT false NOT NULL,
	created_by_user_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_organizations PRIMARY KEY (id),
	CONSTRAINT uq_organizations_slug UNIQUE (slug),
	CONSTRAINT fk_organizations_created_by_user_id_profiles FOREIGN KEY(created_by_user_id) REFERENCES profiles (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_organizations_name ON organizations (name);

CREATE INDEX ix_organizations_created_by_user_id ON organizations (created_by_user_id);


CREATE TABLE media_assets (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	uploaded_by_user_id UUID NOT NULL,
	bucket VARCHAR(100) NOT NULL,
	object_key VARCHAR(1024) NOT NULL,
	original_filename VARCHAR(255),
	content_type VARCHAR(120) NOT NULL,
	size_bytes INTEGER NOT NULL,
	checksum_sha256 VARCHAR(64),
	width INTEGER,
	height INTEGER,
	status media_status DEFAULT 'UPLOADING' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	ready_at TIMESTAMP WITH TIME ZONE,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_media_assets PRIMARY KEY (id),
	CONSTRAINT ck_media_assets_non_negative_size CHECK (size_bytes >= 0),
	CONSTRAINT ck_media_assets_positive_width CHECK (width IS NULL OR width > 0),
	CONSTRAINT ck_media_assets_positive_height CHECK (height IS NULL OR height > 0),
	CONSTRAINT storage_object UNIQUE (bucket, object_key),
	CONSTRAINT fk_media_assets_uploaded_by_user_id_profiles FOREIGN KEY(uploaded_by_user_id) REFERENCES profiles (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_media_assets_uploader_created ON media_assets (uploaded_by_user_id, created_at);

CREATE INDEX ix_media_assets_status_created ON media_assets (status, created_at);


CREATE TABLE events (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	slug VARCHAR(160) NOT NULL,
	title VARCHAR(200) NOT NULL,
	summary VARCHAR(500),
	description TEXT NOT NULL,
	search_document TSVECTOR GENERATED ALWAYS AS (setweight(to_tsvector('russian', coalesce(title, '')), 'A') || setweight(to_tsvector('russian', coalesce(summary, '')), 'B') || setweight(to_tsvector('russian', coalesce(description, '')), 'C')) STORED NOT NULL,
	origin event_origin NOT NULL,
	status event_status DEFAULT 'DRAFT' NOT NULL,
	visibility event_visibility DEFAULT 'PUBLIC' NOT NULL,
	join_policy event_join_policy DEFAULT 'OPEN' NOT NULL,
	format event_format NOT NULL,
	price_type event_price_type DEFAULT 'FREE' NOT NULL,
	price_min NUMERIC(12, 2),
	price_max NUMERIC(12, 2),
	currency VARCHAR(3),
	capacity INTEGER,
	location_id UUID,
	online_url TEXT,
	registration_url TEXT,
	organizer_user_id UUID,
	organizer_organization_id UUID,
	created_by_user_id UUID,
	published_at TIMESTAMP WITH TIME ZONE,
	cancelled_at TIMESTAMP WITH TIME ZONE,
	completed_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT pk_events PRIMARY KEY (id),
	CONSTRAINT ck_events_positive_capacity CHECK (capacity IS NULL OR capacity > 0),
	CONSTRAINT ck_events_organizer_matches_origin CHECK ((origin = 'USER' AND organizer_user_id IS NOT NULL AND organizer_organization_id IS NULL) OR (origin = 'ORGANIZATION' AND organizer_user_id IS NULL AND organizer_organization_id IS NOT NULL) OR (origin = 'EXTERNAL' AND organizer_user_id IS NULL)),
	CONSTRAINT ck_events_location_matches_format CHECK ((format = 'OFFLINE' AND location_id IS NOT NULL AND online_url IS NULL) OR (format = 'ONLINE' AND location_id IS NULL AND online_url IS NOT NULL) OR (format = 'HYBRID' AND location_id IS NOT NULL AND online_url IS NOT NULL)),
	CONSTRAINT ck_events_price_fields_match_type CHECK ((price_type = 'FREE' AND price_min IS NULL AND price_max IS NULL AND currency IS NULL) OR (price_type = 'PAID' AND price_min IS NOT NULL AND price_min >= 0 AND (price_max IS NULL OR price_max >= price_min) AND currency IS NOT NULL)),
	CONSTRAINT uq_events_slug UNIQUE (slug),
	CONSTRAINT fk_events_location_id_locations FOREIGN KEY(location_id) REFERENCES locations (id) ON DELETE SET NULL,
	CONSTRAINT fk_events_organizer_user_id_profiles FOREIGN KEY(organizer_user_id) REFERENCES profiles (id) ON DELETE RESTRICT,
	CONSTRAINT fk_events_organizer_organization_id_organizations FOREIGN KEY(organizer_organization_id) REFERENCES organizations (id) ON DELETE RESTRICT,
	CONSTRAINT fk_events_created_by_user_id_profiles FOREIGN KEY(created_by_user_id) REFERENCES profiles (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_events_organizer_user_status ON events (organizer_user_id, status);

CREATE INDEX ix_events_discovery ON events (status, visibility, published_at);

CREATE INDEX ix_events_location_status ON events (location_id, status);

CREATE INDEX ix_events_price ON events (price_type, price_min, price_max);

CREATE INDEX ix_events_organizer_organization_status ON events (organizer_organization_id, status);

CREATE INDEX ix_events_search_document ON events USING gin (search_document);


CREATE TABLE organization_members (
	organization_id UUID NOT NULL,
	user_id UUID NOT NULL,
	role organization_role NOT NULL,
	joined_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_organization_members PRIMARY KEY (organization_id, user_id),
	CONSTRAINT fk_organization_members_organization_id_organizations FOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE,
	CONSTRAINT fk_organization_members_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_organization_members_user_role ON organization_members (user_id, role);


CREATE TABLE event_favorites (
	user_id UUID NOT NULL,
	event_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_favorites PRIMARY KEY (user_id, event_id),
	CONSTRAINT fk_event_favorites_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_favorites_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_event_favorites_event_created_at ON event_favorites (event_id, created_at);


CREATE TABLE event_dismissals (
	user_id UUID NOT NULL,
	event_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_dismissals PRIMARY KEY (user_id, event_id),
	CONSTRAINT fk_event_dismissals_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_dismissals_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_event_dismissals_event_created_at ON event_dismissals (event_id, created_at);


CREATE TABLE event_managers (
	event_id UUID NOT NULL,
	user_id UUID NOT NULL,
	role event_manager_role DEFAULT 'MANAGER' NOT NULL,
	assigned_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_managers PRIMARY KEY (event_id, user_id),
	CONSTRAINT fk_event_managers_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_managers_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_event_managers_user_role ON event_managers (user_id, role);


CREATE TABLE event_topics (
	event_id UUID NOT NULL,
	topic_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_topics PRIMARY KEY (event_id, topic_id),
	CONSTRAINT fk_event_topics_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_topics_topic_id_topics FOREIGN KEY(topic_id) REFERENCES topics (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_event_topics_topic_event ON event_topics (topic_id, event_id);


CREATE TABLE recurrence_rules (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	event_id UUID NOT NULL,
	timezone VARCHAR(64) NOT NULL,
	dtstart TIMESTAMP WITH TIME ZONE NOT NULL,
	duration_minutes INTEGER,
	rrule TEXT NOT NULL,
	generate_until TIMESTAMP WITH TIME ZONE,
	is_active BOOLEAN DEFAULT true NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_recurrence_rules PRIMARY KEY (id),
	CONSTRAINT ck_recurrence_rules_positive_duration CHECK (duration_minutes IS NULL OR duration_minutes > 0),
	CONSTRAINT uq_recurrence_rules_event_id UNIQUE (event_id),
	CONSTRAINT fk_recurrence_rules_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE
)

;


CREATE TABLE external_event_links (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	event_id UUID NOT NULL,
	source_id UUID NOT NULL,
	external_id VARCHAR(255) NOT NULL,
	external_url TEXT,
	raw_payload JSONB,
	first_imported_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_external_event_links PRIMARY KEY (id),
	CONSTRAINT source_external_id UNIQUE (source_id, external_id),
	CONSTRAINT event_source UNIQUE (event_id, source_id),
	CONSTRAINT fk_external_event_links_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
	CONSTRAINT fk_external_event_links_source_id_external_sources FOREIGN KEY(source_id) REFERENCES external_sources (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_external_event_links_last_synced ON external_event_links (last_synced_at);


CREATE TABLE event_media (
	event_id UUID NOT NULL,
	media_id UUID NOT NULL,
	role event_media_role DEFAULT 'GALLERY' NOT NULL,
	sort_order INTEGER DEFAULT 0 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_media PRIMARY KEY (event_id, media_id),
	CONSTRAINT fk_event_media_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_media_media_id_media_assets FOREIGN KEY(media_id) REFERENCES media_assets (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_event_media_event_role_sort ON event_media (event_id, role, sort_order);

CREATE UNIQUE INDEX uq_event_media_cover ON event_media (event_id) WHERE role = 'COVER';


CREATE TABLE event_occurrences (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	event_id UUID NOT NULL,
	recurrence_rule_id UUID,
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ends_at TIMESTAMP WITH TIME ZONE,
	timezone VARCHAR(64) NOT NULL,
	is_all_day BOOLEAN DEFAULT false NOT NULL,
	status occurrence_status DEFAULT 'SCHEDULED' NOT NULL,
	capacity_override INTEGER,
	cancelled_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_occurrences PRIMARY KEY (id),
	CONSTRAINT ck_event_occurrences_valid_time_range CHECK (ends_at IS NULL OR ends_at > starts_at),
	CONSTRAINT ck_event_occurrences_positive_capacity_override CHECK (capacity_override IS NULL OR capacity_override > 0),
	CONSTRAINT event_start UNIQUE (event_id, starts_at),
	CONSTRAINT fk_event_occurrences_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_occurrences_recurrence_rule_id_recurrence_rules FOREIGN KEY(recurrence_rule_id) REFERENCES recurrence_rules (id) ON DELETE SET NULL
)

;

CREATE INDEX ix_event_occurrences_status_starts_at ON event_occurrences (status, starts_at);

CREATE INDEX ix_event_occurrences_recurrence_starts_at ON event_occurrences (recurrence_rule_id, starts_at);


CREATE TABLE event_participations (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	occurrence_id UUID NOT NULL,
	user_id UUID NOT NULL,
	status participation_status NOT NULL,
	requested_at TIMESTAMP WITH TIME ZONE,
	decided_at TIMESTAMP WITH TIME ZONE,
	decided_by_user_id UUID,
	joined_at TIMESTAMP WITH TIME ZONE,
	cancelled_at TIMESTAMP WITH TIME ZONE,
	rejection_reason VARCHAR(500),
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_participations PRIMARY KEY (id),
	CONSTRAINT occurrence_user UNIQUE (occurrence_id, user_id),
	CONSTRAINT fk_event_participations_occurrence_id_event_occurrences FOREIGN KEY(occurrence_id) REFERENCES event_occurrences (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_participations_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_participations_decided_by_user_id_profiles FOREIGN KEY(decided_by_user_id) REFERENCES profiles (id) ON DELETE SET NULL
)

;

CREATE INDEX ix_event_participations_user_status_created ON event_participations (user_id, status, created_at);

CREATE INDEX ix_event_participations_occurrence_status ON event_participations (occurrence_id, status);


CREATE TABLE event_invitations (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	occurrence_id UUID NOT NULL,
	inviter_user_id UUID NOT NULL,
	invitee_user_id UUID NOT NULL,
	status invitation_status DEFAULT 'PENDING' NOT NULL,
	message VARCHAR(500),
	expires_at TIMESTAMP WITH TIME ZONE,
	responded_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_invitations PRIMARY KEY (id),
	CONSTRAINT ck_event_invitations_different_users CHECK (inviter_user_id <> invitee_user_id),
	CONSTRAINT occurrence_invitee UNIQUE (occurrence_id, invitee_user_id),
	CONSTRAINT fk_event_invitations_occurrence_id_event_occurrences FOREIGN KEY(occurrence_id) REFERENCES event_occurrences (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_invitations_inviter_user_id_profiles FOREIGN KEY(inviter_user_id) REFERENCES profiles (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_invitations_invitee_user_id_profiles FOREIGN KEY(invitee_user_id) REFERENCES profiles (id) ON DELETE CASCADE
)

;

CREATE INDEX ix_event_invitations_inviter_created ON event_invitations (inviter_user_id, created_at);

CREATE INDEX ix_event_invitations_invitee_status ON event_invitations (invitee_user_id, status, created_at);


CREATE TABLE event_interactions (
	id BIGSERIAL NOT NULL,
	user_id UUID NOT NULL,
	event_id UUID NOT NULL,
	occurrence_id UUID,
	type interaction_type NOT NULL,
	request_id UUID,
	session_id UUID,
	feed_kind VARCHAR(40),
	position INTEGER,
	dwell_ms INTEGER,
	context JSONB,
	occurred_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_interactions PRIMARY KEY (id),
	CONSTRAINT ck_event_interactions_non_negative_position CHECK (position IS NULL OR position >= 0),
	CONSTRAINT ck_event_interactions_non_negative_dwell CHECK (dwell_ms IS NULL OR dwell_ms >= 0),
	CONSTRAINT fk_event_interactions_user_id_profiles FOREIGN KEY(user_id) REFERENCES profiles (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_interactions_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_interactions_occurrence_id_event_occurrences FOREIGN KEY(occurrence_id) REFERENCES event_occurrences (id) ON DELETE SET NULL
)

;

CREATE INDEX ix_event_interactions_request_id ON event_interactions (request_id);

CREATE INDEX ix_event_interactions_user_occurred ON event_interactions (user_id, occurred_at);

CREATE INDEX ix_event_interactions_type_occurred ON event_interactions (type, occurred_at);

CREATE INDEX ix_event_interactions_event_occurred ON event_interactions (event_id, occurred_at);


CREATE TABLE event_stories (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	event_id UUID NOT NULL,
	occurrence_id UUID,
	created_by_user_id UUID NOT NULL,
	status story_status DEFAULT 'DRAFT' NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE,
	expires_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_event_stories PRIMARY KEY (id),
	CONSTRAINT fk_event_stories_event_id_events FOREIGN KEY(event_id) REFERENCES events (id) ON DELETE CASCADE,
	CONSTRAINT fk_event_stories_occurrence_id_event_occurrences FOREIGN KEY(occurrence_id) REFERENCES event_occurrences (id) ON DELETE SET NULL,
	CONSTRAINT fk_event_stories_created_by_user_id_profiles FOREIGN KEY(created_by_user_id) REFERENCES profiles (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_event_stories_creator_created ON event_stories (created_by_user_id, created_at);

CREATE INDEX ix_event_stories_occurrence_status ON event_stories (occurrence_id, status);

CREATE INDEX ix_event_stories_event_status_published ON event_stories (event_id, status, published_at);


CREATE TABLE participation_status_history (
	id BIGSERIAL NOT NULL,
	participation_id UUID NOT NULL,
	from_status participation_status,
	to_status participation_status NOT NULL,
	changed_by_user_id UUID,
	reason VARCHAR(500),
	changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_participation_status_history PRIMARY KEY (id),
	CONSTRAINT fk_participation_status_history_participation_id_event__89f6 FOREIGN KEY(participation_id) REFERENCES event_participations (id) ON DELETE CASCADE,
	CONSTRAINT fk_participation_status_history_changed_by_user_id_profiles FOREIGN KEY(changed_by_user_id) REFERENCES profiles (id) ON DELETE SET NULL
)

;

CREATE INDEX ix_participation_history_actor_changed ON participation_status_history (changed_by_user_id, changed_at);

CREATE INDEX ix_participation_history_participation_changed ON participation_status_history (participation_id, changed_at);


CREATE TABLE story_items (
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	story_id UUID NOT NULL,
	media_id UUID NOT NULL,
	caption VARCHAR(500),
	sort_order INTEGER DEFAULT 0 NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_story_items PRIMARY KEY (id),
	CONSTRAINT fk_story_items_story_id_event_stories FOREIGN KEY(story_id) REFERENCES event_stories (id) ON DELETE CASCADE,
	CONSTRAINT uq_story_items_media_id UNIQUE (media_id),
	CONSTRAINT fk_story_items_media_id_media_assets FOREIGN KEY(media_id) REFERENCES media_assets (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_story_items_story_sort ON story_items (story_id, sort_order);

ALTER TABLE organizations ADD CONSTRAINT fk_organizations_avatar_media_id_media_assets FOREIGN KEY(avatar_media_id) REFERENCES media_assets (id) ON DELETE SET NULL;

ALTER TABLE profiles ADD CONSTRAINT fk_profiles_avatar_media_id_media_assets FOREIGN KEY(avatar_media_id) REFERENCES media_assets (id) ON DELETE SET NULL;
