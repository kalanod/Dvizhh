import { request } from "../api/client";

export type Coordinates = [longitude: number, latitude: number];

type MapErrorStage = "script_load" | "sdk_missing" | "sdk_ready" | "map_init" | "marker_update";

export function reportMapError(stage: MapErrorStage, error: unknown, apiKey = ""): void {
    let message = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    if (apiKey) message = message.replaceAll(apiKey, "[REDACTED]");
    message = message.replace(/(apikey|api_key|key)=[^\s&#"']+/gi, "$1=[REDACTED]").slice(0, 2000);
    const body = { stage, message, online: typeof navigator === "undefined" ? null : navigator.onLine };
    console.error("[Yandex Maps]", { ...body, origin: window.location.origin });
    void request<void>("/maps/client-error", { method: "POST", body }).catch(() => {
        console.warn("[Yandex Maps] Не удалось отправить ошибку в логи backend.");
    });
}

interface MapEntity {
    update(props: Record<string, unknown>): void;
}

export interface MapInstance extends MapEntity {
    addChild(entity: MapEntity): MapInstance;
    removeChild(entity: MapEntity): MapInstance;
    destroy(): void;
}

export interface YandexMaps {
    ready: Promise<void>;
    YMap: new (container: HTMLElement, props: Record<string, unknown>) => MapInstance;
    YMapDefaultSchemeLayer: new (props?: Record<string, unknown>) => MapEntity;
    YMapDefaultFeaturesLayer: new (props?: Record<string, unknown>) => MapEntity;
    YMapMarker: new (props: Record<string, unknown>, element: HTMLElement) => MapEntity;
    YMapListener: new (props: {
        layer: string;
        onClick: (object: { type: string } | undefined, event: { coordinates: Coordinates }) => void;
    }) => MapEntity;
}

declare global {
    interface Window {
        ymaps3?: YandexMaps;
    }
}

let apiPromise: Promise<YandexMaps> | undefined;

export function loadYandexMaps(apiKey: string): Promise<YandexMaps> {
    if (apiPromise) return apiPromise;
    apiPromise = new Promise<YandexMaps>((resolve, reject) => {
        const script = document.createElement("script");
        script.src = `https://api-maps.yandex.ru/v3/?apikey=${encodeURIComponent(apiKey)}&lang=ru_RU`;
        script.async = true;
        script.onload = () => {
            const api = window.ymaps3;
            if (!api) {
                const error = new Error("Скрипт загружен, но объект ymaps3 не создан.");
                reportMapError("sdk_missing", error, apiKey);
                reject(error);
                return;
            }
            api.ready.then(() => resolve(api), (error: unknown) => {
                reportMapError("sdk_ready", error, apiKey);
                reject(error);
            });
        };
        script.onerror = () => {
            script.remove();
            reportMapError("script_load", new Error(
                "Не загружен https://api-maps.yandex.ru/v3/. HTTP-статус недоступен в script.onerror. "
                + "Проверьте запрос в DevTools → Network: статус ответа, DNS/TLS, блокировку расширением или CSP; "
                + "при 401/403 — ключ, подключение JavaScript API и HTTP Referer.",
            ), apiKey);
            reject(new Error("Не удалось загрузить Яндекс Карты. Подробности — в консоли браузера и логах backend."));
        };
        document.head.appendChild(script);
    }).catch((error) => {
        apiPromise = undefined;
        throw error;
    });
    return apiPromise;
}

export function locationCoordinates(latitude: string, longitude: string): Coordinates | null {
    if (!latitude.trim() || !longitude.trim()) return null;
    const lat = Number(latitude);
    const lon = Number(longitude);
    return Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180
        ? [lon, lat] : null;
}
