import type { DvizhEvent } from "./event";
import type { Friendship, Profile } from "./user";

export type NotificationKind = "EVENT_UPDATED" | "EVENT_CANCELLED";
export type InvitationStatus = "PENDING" | "ACCEPTED" | "DECLINED" | "REVOKED" | "EXPIRED";
export type MediaStatus = "UPLOADING" | "READY" | "FAILED" | "DELETED";

/** Уведомление об изменении события (NotificationDTO backend-а). */
export interface DvizhNotification {
    id: string;
    event_id: string;
    actor_id: string | null;
    kind: NotificationKind;
    payload: { title?: string; changed_fields?: string[] };
    created_at: string;
    read_at: string | null;
}

export interface Invitation {
    id: string;
    occurrence_id: string;
    inviter_user_id: string;
    invitee_user_id: string;
    status: InvitationStatus;
    message: string | null;
    expires_at: string | null;
    responded_at: string | null;
    created_at: string;
    updated_at: string;
}

/** Входящее приглашение вместе с карточкой события. */
export interface InvitationCard {
    invitation: Invitation;
    event: DvizhEvent;
}

/** Тело POST /api/events/{id}/invitations. */
export interface CreateInvitationInput {
    actor_id: string;
    invitee_id: string;
    message: string | null;
}

/** Заявка в друзья вместе с профилем второй стороны. */
export interface FriendshipRequest {
    friendship: Friendship;
    user: Profile;
}

export interface Media {
    id: string;
    uploaded_by_user_id: string;
    original_filename: string | null;
    content_type: string;
    size_bytes: number;
    width: number | null;
    height: number | null;
    status: MediaStatus;
    created_at: string;
    content_url: string;
}

/** Личные списки GET /api/users/{id}/events?kind=... */
export type PersonalEventsKind = "organized" | "participating" | "requested";
