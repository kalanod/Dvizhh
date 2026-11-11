import { loadPages } from "./paging";
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

export const revokeInvitation = (invitationId: string, actorId: string) =>
    request<Invitation>(`/invitations/${invitationId}`, { method: "DELETE", query: { actor_id: actorId } });

export const listEventInvitations = (eventId: string, actorId: string, page: Page = {}) =>
    getPage<Invitation>(`/events/${eventId}/invitations`, page, { actor_id: actorId });

interface Page {
    offset?: number;
    limit?: number;
    signal?: AbortSignal;
}

/** GET-запрос личного списка: offset/limit уходят в query, signal — в fetch. */
const getPage = <T>(path: string, { offset, limit, signal }: Page, query: Record<string, string | boolean> = {}) =>
    loadPages<T>(
        (pageOffset, pageLimit) => request(path, { query: { ...query, offset: pageOffset, limit: pageLimit }, signal }),
        limit, offset,
    );

export const updateProfile = (userId: string, body: UpdateProfileInput) =>
    request<Profile>(`/users/${userId}`, { method: "PATCH", body });

export const listMyEvents = (userId: string, kind: PersonalEventsKind, page: Page = {}) =>
    getPage<DvizhEvent>(`/users/${userId}/events`, page, { kind });

export const listDrafts = (userId: string, page: Page = {}) => getPage<DvizhEvent>(`/users/${userId}/drafts`, page);

export const listFavorites = (userId: string, page: Page = {}) => getPage<DvizhEvent>(`/users/${userId}/favorites`, page);

/** Сохранить в избранное или убрать; возвращает обновлённую карточку. */
export const setFavorite = (userId: string, eventId: string, enabled: boolean) =>
    request<DvizhEvent>(`/users/${userId}/favorites/${eventId}`, { method: enabled ? "PUT" : "DELETE" });

export const listDismissed = (userId: string, page: Page = {}) => getPage<DvizhEvent>(`/users/${userId}/dismissed`, page);

/** «Не интересно» убирает событие из ленты этого пользователя; false возвращает его обратно. */
export const setDismissed = (userId: string, eventId: string, enabled: boolean) =>
    request<DvizhEvent>(`/users/${userId}/dismissed/${eventId}`, { method: enabled ? "PUT" : "DELETE" });

export const listFriendRequests = (userId: string, direction: "incoming" | "outgoing", page: Page = {}) =>
    getPage<FriendshipRequest>(`/users/${userId}/friends/requests`, page, { direction });

export const listInvitations = (userId: string, page: Page = {}) =>
    getPage<InvitationCard>(`/users/${userId}/invitations`, page);

export const respondToInvitation = (invitationId: string, userId: string, accept: boolean) =>
    request<Invitation>(`/invitations/${invitationId}`, { method: "PATCH", body: { user_id: userId, accept } });

export const listNotifications = (userId: string, { unreadOnly = false, ...page }: Page & { unreadOnly?: boolean } = {}) =>
    getPage<DvizhNotification>(`/users/${userId}/notifications`, page, { unread_only: unreadOnly });

export const markNotificationRead = (userId: string, notificationId: string) =>
    request<DvizhNotification>(`/users/${userId}/notifications/${notificationId}/read`, { method: "PUT" });


export async function findEventInvitation(userId: string, eventId: string, signal?: AbortSignal) {
    for (let offset = 0; ; offset += 100) {
        const page = await listInvitations(userId, { offset, limit: 100, signal });
        const found = page.find((card) => card.event.id === eventId);
        if (found || page.length < 100) return found ? [found] : [];
    }
}
