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
        },
    });

export const getEvent = (eventId: string) => request<DvizhEvent>(`/events/${eventId}`);

export const createEvent = (body: CreateEventInput) =>
    request<DvizhEvent>("/events", { method: "POST", body });

export const updateEvent = (eventId: string, body: EventInput) =>
    request<DvizhEvent>(`/events/${eventId}`, { method: "PUT", body });

export const deleteEvent = (eventId: string) => request<void>(`/events/${eventId}`, { method: "DELETE" });

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
