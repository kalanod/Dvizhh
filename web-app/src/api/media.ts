import { request } from "./client";
import type { DvizhEvent, Media, Profile } from "../models";

/** Загружает JPEG, PNG или WebP; backend пережимает его в WebP. */
export const uploadMedia = (userId: string, file: File) =>
    request<Media>("/media", { method: "POST", file, query: { user_id: userId, filename: file.name } });

/** media_id = null убирает аватар. */
export const setAvatar = (userId: string, mediaId: string | null) =>
    request<Profile>(`/users/${userId}/avatar`, { method: "PUT", body: { media_id: mediaId } });

/** media_id = null убирает обложку. */
export const setCover = (eventId: string, actorId: string, mediaId: string | null) =>
    request<DvizhEvent>(`/events/${eventId}/cover`, {
        method: "PUT",
        body: { media_id: mediaId },
        query: { actor_id: actorId },
    });

/**
 * Адрес картинки для <img>. Публичные аватары и обложки доступны всем,
 * а обложки черновиков и закрытых событий — только с viewer_id.
 */
export const mediaSrc = (url: string | null | undefined, viewerId?: string | null) => {
    if (!url) return null;
    return viewerId ? `${url}?viewer_id=${encodeURIComponent(viewerId)}` : url;
};
