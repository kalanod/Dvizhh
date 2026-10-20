import type { UserSummary } from "./user";

export type EventFormat = "OFFLINE" | "ONLINE" | "HYBRID";
export type EventPriceType = "FREE" | "PAID";
export type EventStatus = "DRAFT" | "PUBLISHED" | "CANCELLED" | "COMPLETED" | "ARCHIVED";
export type EventVisibility = "PUBLIC" | "FRIENDS" | "UNLISTED" | "PRIVATE";
export type EventJoinPolicy = "OPEN" | "REQUEST" | "INVITE_ONLY" | "EXTERNAL";
export type ParticipationStatus = "REQUESTED" | "GOING" | "REJECTED" | "CANCELLED";

// Decimal-поля backend сериализует строками.
export interface EventLocation {
    name: string | null;
    city: string | null;
    address_line: string | null;
    latitude: string;
    longitude: string;
}

/** Событие в формате EventDTO backend-а. */
export interface DvizhEvent {
    id: string;
    occurrence_id: string;
    slug: string;
    title: string;
    description: string;
    tags: string[];
    starts_at: string;
    ends_at: string | null;
    timezone: string;
    is_all_day: boolean;
    format: EventFormat;
    location: EventLocation | null;
    online_url: string | null;
    registration_url: string | null;
    price_type: EventPriceType;
    price_min: string | null;
    price_max: string | null;
    currency: string | null;
    capacity: number | null;
    participants_count: number;
    status: EventStatus;
    visibility: EventVisibility;
    join_policy: EventJoinPolicy;
    organizer: UserSummary | null;
    published_at: string | null;
    created_at: string;
}

export interface EventLocationInput {
    name: string | null;
    city: string | null;
    address_line: string | null;
    latitude: string;
    longitude: string;
}

/** Тело PUT /api/events/{id} (UpdateEventDTO). */
export interface EventInput {
    title: string;
    description: string;
    tags: string[];
    starts_at: string;
    ends_at: string | null;
    timezone: string;
    is_all_day: boolean;
    format: EventFormat;
    location: EventLocationInput | null;
    online_url: string | null;
    registration_url: string | null;
    price_min: string | null;
    price_max: string | null;
    currency: string;
    capacity: number | null;
    visibility: EventVisibility;
    join_policy: EventJoinPolicy;
}

/** Тело POST /api/events (CreateEventDTO). */
export interface CreateEventInput extends EventInput {
    organizer_id: string;
}

export interface Participant {
    user: UserSummary;
    status: ParticipationStatus;
}

/** Параметры ленты GET /api/events. */
export interface EventFilters {
    q?: string;
    tag?: string;
    from?: string;
    to?: string;
    freeOnly?: boolean;
    availableOnly?: boolean;
    friendsOf?: string;
    offset?: number;
    limit?: number;
}
