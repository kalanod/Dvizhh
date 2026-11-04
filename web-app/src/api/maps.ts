import { request } from "./client";
import type { Coordinates } from "../utils/yandexMaps";

export interface MapsConfig {
    api_key: string;
    search_enabled: boolean;
}

export interface AddressSuggestion {
    title: string;
    subtitle: string;
    address: string;
    uri: string;
    kind: "geo" | "biz";
    city?: string | null;
}

export interface GeocodedPlace {
    name?: string | null;
    address_line: string;
    city: string | null;
    latitude: string;
    longitude: string;
}

export const getMapsConfig = (signal?: AbortSignal) => request<MapsConfig>("/maps/config", { signal });

export const suggestAddresses = (text: string, city: string, signal?: AbortSignal, center?: Coordinates | null) =>
    request<AddressSuggestion[]>("/maps/suggest", {
        query: { text, city, longitude: center?.[0], latitude: center?.[1] }, signal,
    });

export const geocodeAddress = (query: string, uri = "", signal?: AbortSignal) =>
    request<GeocodedPlace>("/maps/geocode", { query: { query, uri }, signal });
