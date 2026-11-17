import type { Coordinates } from "./yandexMaps";

export interface DiscoveryCamera { center: Coordinates; zoom: number }
const MAX_LATITUDE = 85.0511287798066;
const project = ([longitude, latitude]: Coordinates): Coordinates => {
    const phi = Math.max(-MAX_LATITUDE, Math.min(MAX_LATITUDE, latitude)) * Math.PI / 180;
    return [(longitude + 180) / 360, (1 - Math.log(Math.tan(phi) + 1 / Math.cos(phi)) / Math.PI) / 2];
};
const unproject = ([x, y]: Coordinates): Coordinates => [
    ((x * 360) % 360 + 360) % 360 - 180,
    Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180 / Math.PI,
];

/** Bias toward the user at a comfortable scale; fit both points with pixel padding. */
export function initialDiscoveryCamera(origin: Coordinates, nearest: Coordinates | null, width: number, height: number): DiscoveryCamera {
    const user = project(origin);
    if (!nearest) return { center: unproject(user), zoom: 12 };
    const target = project(nearest);
    const dx = ((target[0] - user[0] + 1.5) % 1) - 0.5;
    const dy = target[1] - user[1];
    const safeWidth = Math.max(32, width - 96);
    const safeHeight = Math.max(32, height - 96);
    const defaultScale = 256 * 2 ** 12;
    const separation = Math.max(2 * Math.abs(dx) * defaultScale / safeWidth, 2 * Math.abs(dy) * defaultScale / safeHeight);
    const bias = separation <= 1 ? 0 : (1 - 1 / separation ** 2) / 2;
    const center: Coordinates = [user[0] + dx * bias, user[1] + dy * bias];
    const spanX = 2 * Math.max(Math.abs(dx * bias), Math.abs(dx * (1 - bias)));
    const spanY = 2 * Math.max(Math.abs(dy * bias), Math.abs(dy * (1 - bias)));
    const scale = Math.min(spanX ? safeWidth / (256 * spanX) : Infinity, spanY ? safeHeight / (256 * spanY) : Infinity);
    return { center: unproject(center), zoom: Math.max(0, Math.min(12, Math.log2(scale))) };
}
