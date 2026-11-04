import { request } from "./client";

export interface MapsConfig {
    api_key: string;
    search_enabled: boolean;
}

export interface AddressSuggestion {
    title: string;
    subtitle: string;
    address: string;
    uri: string;
}

export interface GeocodedPlace {
    address_line: string;
    city: string | null;
    latitude: string;
    longitude: string;
}

export const getMapsConfig = (signal?: AbortSignal) => request<MapsConfig>("/maps/config", { signal });

export const suggestAddresses = (text: string, city: string, signal?: AbortSignal) =>
    request<AddressSuggestion[]>("/maps/suggest", { query: { text, city }, signal });

export const geocodeAddress = (query: string, uri = "", signal?: AbortSignal) =>
    request<GeocodedPlace>("/maps/geocode", { query: { query, uri }, signal });
