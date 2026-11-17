import { ApiError, request } from "./client";
import type { DvizhEvent, EventSort } from "../models";

export interface DiscoveryBounds { west: number; south: number; east: number; north: number }
export interface DiscoveryViewport extends DiscoveryBounds {
    zoom: number;
    center: { longitude: number; latitude: number };
}
export type DiscoverySort = EventSort;
export interface DiscoveryRequest {
    filters: {
        q?: string; tag_id?: string | null; date_from?: string | null; date_to?: string | null;
        free_only?: boolean; available_only?: boolean; friends_of?: string | null; viewer_id?: string | null;
    };
    viewport: DiscoveryViewport | null;
    origin?: { latitude: number; longitude: number } | null;
    sort: DiscoverySort;
    selection_token: string | null;
    cursor: string | null;
    limit: number;
    include_map: boolean;
}
export interface DiscoveryMapItem {
    id: string;
    type: "event" | "cluster";
    longitude: number;
    latitude: number;
    count: number;
    state?: "default" | "going" | "organizer" | "favorite";
    title?: string | null;
    event_id: string | null;
    selection_token: string | null;
    bounds: DiscoveryBounds;
}
export interface DiscoveryResponse {
    as_of: string;
    map: { items: DiscoveryMapItem[]; total_events: number } | null;
    feed: { items: DvizhEvent[]; total_events: number; next_cursor: string | null };
}

export const bootstrapDiscovery = (filters: DiscoveryRequest["filters"], origin: { latitude: number; longitude: number }, signal?: AbortSignal) =>
    request<{ nearest: { event_id: string; point: { latitude: number; longitude: number } } | null }>("/events/discovery/bootstrap", { method: "POST", body: { filters, origin }, signal });
export const discoverEvents = async (body: DiscoveryRequest, signal?: AbortSignal) => {
    const response = await request<DiscoveryResponse>("/events/discovery", { method: "POST", body, signal });
    if (response.map && (response.map.items.length > 30
        || new Set(response.map.items.map((item) => item.id)).size !== response.map.items.length
        || response.map.items.reduce((total, item) => total + item.count, 0) !== response.map.total_events
        || response.map.items.some((item) =>
        !Number.isFinite(item.longitude) || Math.abs(item.longitude) > 180
        || !Number.isFinite(item.latitude) || Math.abs(item.latitude) > 90
        || !Number.isInteger(item.count) || item.count < 1
        || (item.state !== undefined && !["default", "going", "organizer", "favorite"].includes(item.state))
        || (item.title !== undefined && item.title !== null && typeof item.title !== "string")
        || (item.type === "event" ? item.count !== 1 || !item.event_id || item.selection_token !== null
            : item.type !== "cluster" || item.count <= 1 || !item.selection_token || item.event_id !== null)))) {
        throw new ApiError("Не удалось получить корректные данные карты. Попробуйте обновить выдачу.", 502);
    }
    return response;
};
