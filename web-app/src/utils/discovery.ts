import { discoverEvents, type DiscoveryRequest, type DiscoveryResponse, type DiscoveryViewport } from "../api/discovery";
import type { DvizhEvent } from "../models";

/** Full server representations only: merging partial clusters would invalidate their counts/cap. */
export class DiscoveryCache {
    private values = new Map<string, { response: DiscoveryResponse; expires: number }>();
    private pending = new Map<string, { controller: AbortController; promise: Promise<DiscoveryResponse>; users: number }>();
    private readonly load: typeof discoverEvents;
    private readonly ttl: number;
    private readonly capacity: number;
    private readonly now: () => number;
    private generation = 0;
    constructor(load = discoverEvents, ttl = 60_000, capacity = 30, now = Date.now) {
        this.load = load; this.ttl = ttl; this.capacity = capacity; this.now = now;
    }

    clear() { this.values.clear(); this.pending.clear(); this.generation++; }

    async get(body: DiscoveryRequest, signal: AbortSignal, refresh = false): Promise<DiscoveryResponse> {
        signal.throwIfAborted();
        const key = JSON.stringify(body);
        const cached = this.values.get(key);
        if (!refresh && cached && cached.expires > this.now()) {
            this.values.delete(key); this.values.set(key, cached);
            return cached.response;
        }
        this.values.delete(key);
        let entry = this.pending.get(key);
        if (!entry) {
            const controller = new AbortController();
            const generation = this.generation;
            const promise = this.load(body, controller.signal).then((response) => {
                if (!controller.signal.aborted && generation === this.generation) {
                    this.values.delete(key);
                    this.values.set(key, { response, expires: this.now() + this.ttl });
                    while (this.values.size > this.capacity) this.values.delete(this.values.keys().next().value!);
                }
                return response;
            }).finally(() => { if (this.pending.get(key)?.controller === controller) this.pending.delete(key); });
            entry = { controller, promise, users: 0 };
            this.pending.set(key, entry);
        }
        const active = entry;
        active.users++;
        return new Promise((resolve, reject) => {
            let finished = false;
            const cleanup = () => {
                if (finished) return false;
                finished = true;
                signal.removeEventListener("abort", abort);
                active.users--;
                if (active.users === 0) {
                    if (this.pending.get(key) === active) this.pending.delete(key);
                    active.controller.abort();
                }
                return true;
            };
            const abort = () => { if (cleanup()) reject(signal.reason ?? new DOMException("Aborted", "AbortError")); };
            signal.addEventListener("abort", abort, { once: true });
            active.promise.then((value) => { if (cleanup()) resolve(value); }, (error: unknown) => { if (cleanup()) reject(error); });
            if (signal.aborted) abort();
        });
    }
}

export const discoveryCache = new DiscoveryCache();

export function mergeDiscoveryEvents(previous: DvizhEvent[], incoming: DvizhEvent[]) {
    const events = new Map(previous.map((event) => [event.id, event]));
    for (const event of incoming) events.set(event.id, event);
    return [...events.values()];
}

const longitude = (value: number) => ((value + 180) % 360 + 360) % 360 - 180;
export function discoveryViewport(bounds: [[number, number], [number, number]], center: [number, number], zoom: number): DiscoveryViewport | null {
    if (![...bounds[0], ...bounds[1], ...center, zoom].every(Number.isFinite)) return null;
    const round = (value: number) => Number(value.toFixed(6));
    const south = round(Math.max(-90, Math.min(bounds[0][1], bounds[1][1])));
    const north = round(Math.min(90, Math.max(bounds[0][1], bounds[1][1])));
    const world = Math.abs(bounds[1][0] - bounds[0][0]) >= 359.999999;
    const west = world ? -180 : round(longitude(bounds[0][0]));
    const east = world ? 180 : round(longitude(bounds[1][0]));
    if (south >= north || west === east) return null;
    return { west, south, east, north, zoom: Number(Math.max(0, Math.min(23, zoom)).toFixed(2)),
        center: { longitude: round(longitude(center[0])), latitude: round(Math.max(-90, Math.min(90, center[1]))) } };
}
