import { request } from "./client";
import type { DvizhEvent, Profile } from "../models";

export interface MediaConfig {
    max_bytes: number;
    max_pixels: number;
    formats: string[];
}

export interface UploadedMedia {
    id: string;
    content_url: string;
    content_type: string;
    size_bytes: number;
    width: number;
    height: number;
}

export const getMediaConfig = () => request<MediaConfig>("/media/config");

export const uploadImage = (userId: string, file: File) =>
    request<UploadedMedia>("/media", {
        method: "POST",
        rawBody: file,
        query: { user_id: userId, filename: file.name },
    });

export const setEventCover = (eventId: string, actorId: string, mediaId: string | null) =>
    request<DvizhEvent>(`/events/${eventId}/cover`, {
        method: "PUT",
        query: { actor_id: actorId },
        body: { media_id: mediaId },
    });

export const setAvatar = (userId: string, mediaId: string | null) =>
    request<Profile>(`/users/${userId}/avatar`, { method: "PUT", body: { media_id: mediaId } });
