import { request } from "./client";
import type {
    DvizhEvent,
    DvizhNotification,
    FriendshipRequest,
    Invitation,
    InvitationCard,
    PersonalEventsKind,
    Profile,
    UpdateProfileInput,
} from "../models";

interface Page {
    offset?: number;
    limit?: number;
}

export const updateProfile = (userId: string, body: UpdateProfileInput) =>
    request<Profile>(`/users/${userId}`, { method: "PATCH", body });

export const listMyEvents = (userId: string, kind: PersonalEventsKind, page: Page = {}) =>
    request<DvizhEvent[]>(`/users/${userId}/events`, { query: { kind, ...page } });

export const listDrafts = (userId: string, page: Page = {}) =>
    request<DvizhEvent[]>(`/users/${userId}/drafts`, { query: { ...page } });

export const listFavorites = (userId: string, page: Page = {}) =>
    request<DvizhEvent[]>(`/users/${userId}/favorites`, { query: { ...page } });

/** Сохранить в избранное или убрать; возвращает обновлённую карточку. */
export const setFavorite = (userId: string, eventId: string, enabled: boolean) =>
    request<DvizhEvent>(`/users/${userId}/favorites/${eventId}`, { method: enabled ? "PUT" : "DELETE" });

export const listDismissed = (userId: string, page: Page = {}) =>
    request<DvizhEvent[]>(`/users/${userId}/dismissed`, { query: { ...page } });

/** «Не интересно» убирает событие из ленты этого пользователя; false возвращает его обратно. */
export const setDismissed = (userId: string, eventId: string, enabled: boolean) =>
    request<DvizhEvent>(`/users/${userId}/dismissed/${eventId}`, { method: enabled ? "PUT" : "DELETE" });

export const listFriendRequests = (userId: string, direction: "incoming" | "outgoing", page: Page = {}) =>
    request<FriendshipRequest[]>(`/users/${userId}/friends/requests`, { query: { direction, ...page } });

export const listInvitations = (userId: string, page: Page = {}) =>
    request<InvitationCard[]>(`/users/${userId}/invitations`, { query: { ...page } });

export const respondToInvitation = (invitationId: string, userId: string, accept: boolean) =>
    request<Invitation>(`/invitations/${invitationId}`, { method: "PATCH", body: { user_id: userId, accept } });

export const listNotifications = (userId: string, { unreadOnly = false, ...page }: Page & { unreadOnly?: boolean } = {}) =>
    request<DvizhNotification[]>(`/users/${userId}/notifications`, { query: { unread_only: unreadOnly, ...page } });

export const markNotificationRead = (userId: string, notificationId: string) =>
    request<DvizhNotification>(`/users/${userId}/notifications/${notificationId}/read`, { method: "PUT" });
