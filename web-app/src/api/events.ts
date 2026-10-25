import { request } from "./client";
import type {
    CreateEventInput,
    CreateInvitationInput,
    DvizhEvent,
    EventFilters,
    EventInput,
    Invitation,
    Participant,
} from "../models";

export const listEvents = (filters: EventFilters = {}, signal?: AbortSignal) =>
    request<DvizhEvent[]>("/events", {
        signal,
        query: {
            q: filters.q,
            tag: filters.tag,
            from: filters.from,
            to: filters.to,
            free_only: filters.freeOnly,
            available_only: filters.availableOnly,
            friends_of: filters.friendsOf,
            offset: filters.offset,
            limit: filters.limit,
            viewer_id: filters.viewerId,
        },
    });

export const getEvent = (eventId: string, viewerId?: string | null, signal?: AbortSignal) =>
    request<DvizhEvent>(`/events/${eventId}`, { query: { viewer_id: viewerId }, signal });

export const createEvent = (body: CreateEventInput) =>
    request<DvizhEvent>("/events", { method: "POST", body });

/** Черновик не попадает в ленту, пока его не опубликуют. */
export const createDraft = (body: CreateEventInput) =>
    request<DvizhEvent>("/events/drafts", { method: "POST", body });

export const publishEvent = (eventId: string, actorId: string) =>
    request<DvizhEvent>(`/events/${eventId}/publish`, { method: "POST", body: { actor_id: actorId } });

/** Отмена уведомляет участников, заявителей, приглашённых и тех, кто сохранил событие. */
export const cancelEvent = (eventId: string, actorId: string) =>
    request<DvizhEvent>(`/events/${eventId}/cancel`, { method: "POST", body: { actor_id: actorId } });

export const inviteToEvent = (eventId: string, body: CreateInvitationInput) =>
    request<Invitation>(`/events/${eventId}/invitations`, { method: "POST", body });

export const updateEvent =(eventId: string, body: EventInput, actorId: string) =>
    request<DvizhEvent>(`/events/${eventId}`, { method: "PUT", body, query: { actor_id: actorId } });

export const deleteEvent = (eventId: string, actorId: string) =>
    request<void>(`/events/${eventId}`, { method: "DELETE", query: { actor_id: actorId } });

export const listParticipants = (eventId: string, signal?: AbortSignal) =>
    request<Participant[]>(`/events/${eventId}/participants`, { signal });

export const joinEvent = (eventId: string, userId: string) =>
    request<Participant>(`/events/${eventId}/participants`, { method: "POST", body: { user_id: userId } });

export const reviewParticipation = (eventId: string, userId: string, actorId: string, accept: boolean) =>
    request<Participant>(`/events/${eventId}/participants/${userId}`, {
        method: "PATCH",
        body: { actor_id: actorId, accept },
    });

export const leaveEvent = (eventId: string, userId: string) =>
    request<void>(`/events/${eventId}/participants/${userId}`, { method: "DELETE" });
