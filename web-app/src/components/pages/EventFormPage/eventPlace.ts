import type { EventLocationInput } from "../../../models";
import type { GeocodedPlace } from "../../../api/maps";
import { locationCoordinates, type Coordinates } from "../../../utils/yandexMaps";
import { formatLocationLabel } from "../../../utils/format";

/** Search text is never parsed into address components. Only a selected/saved snapshot has metadata. */
export type EventPlaceValue =
    | { kind: "text"; text: string }
    | { kind: "resolved"; text: string; location: EventLocationInput };

export const textPlace = (text = ""): EventPlaceValue => ({ kind: "text", text });
const clean = (value: string | null | undefined) => value?.trim() || null;
const coordinate = (value: string | null) => {
    const text = clean(value);
    if (text === null) return null;
    const number = Number(text.replace(",", "."));
    return Number.isFinite(number) ? number.toFixed(6) : text;
};

export function placeDisplayText(location: EventLocationInput): string {
    return formatLocationLabel(location) || "Точка на карте";
}

export const placeFromLocation = (location: EventLocationInput | null): EventPlaceValue => location
    ? { kind: "resolved", text: placeDisplayText(location), location: { ...location } }
    : textPlace();

export const placeFromGeocode = (place: GeocodedPlace, point?: Coordinates): EventPlaceValue => {
    const coordinates = point ?? locationCoordinates(place.latitude, place.longitude);
    if (!coordinates) throw new Error("Не удалось определить точку выбранного места.");
    return placeFromLocation({
        name: clean(place.name), city: clean(place.city), address_line: clean(place.address_line),
        latitude: coordinates[1].toFixed(6), longitude: coordinates[0].toFixed(6),
    });
};

export const pointPlace = (point: Coordinates): EventPlaceValue => placeFromLocation({
    name: null, city: null, address_line: null,
    latitude: point[1].toFixed(6), longitude: point[0].toFixed(6),
});

export function placeToLocation(place: EventPlaceValue): EventLocationInput | null {
    if (place.kind === "text") {
        const text = clean(place.text);
        return text ? { name: null, city: null, address_line: text, latitude: null, longitude: null } : null;
    }
    return {
        name: clean(place.location.name), city: clean(place.location.city),
        address_line: clean(place.location.address_line),
        latitude: coordinate(place.location.latitude), longitude: coordinate(place.location.longitude),
    };
}

export const placeCoordinates = (place: EventPlaceValue): Coordinates | null => place.kind === "resolved"
    ? locationCoordinates(place.location.latitude ?? "", place.location.longitude ?? "") : null;

export const placeContextUnchanged = (place: EventPlaceValue, initial: EventPlaceValue) => JSON.stringify(place) === JSON.stringify(initial);
