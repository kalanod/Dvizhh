import { request } from "./client";
import type { CreateEventInput, DvizhEvent, EventFilters, EventInput, Participant } from "../models";

export const listEvents = (filters: EventFilters = {}) =>
    request<DvizhEvent[]>("/events", {
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

export const getEvent = (eventId: string, viewerId?: string | null) =>
    request<DvizhEvent>(`/events/${eventId}`, { query: { viewer_id: viewerId } });

export const createEvent = (body: CreateEventInput) =>
    request<DvizhEvent>("/events", { method: "POST", body });

export const updateEvent = (eventId: string, body: EventInput, actorId: string) =>
    request<DvizhEvent>(`/events/${eventId}`, { method: "PUT", body, query: { actor_id: actorId } });

export const deleteEvent = (eventId: string, actorId: string) =>
    request<void>(`/events/${eventId}`, { method: "DELETE", query: { actor_id: actorId } });

export const listParticipants = (eventId: string) =>
    request<Participant[]>(`/events/${eventId}/participants`);

export const joinEvent = (eventId: string, userId: string) =>
    request<Participant>(`/events/${eventId}/participants`, { method: "POST", body: { user_id: userId } });

export const reviewParticipation = (eventId: string, userId: string, actorId: string, accept: boolean) =>
    request<Participant>(`/events/${eventId}/participants/${userId}`, {
        method: "PATCH",
        body: { actor_id: actorId, accept },
    });

export const leaveEvent = (eventId: string, userId: string) =>
    request<void>(`/events/${eventId}/participants/${userId}`, { method: "DELETE" });
