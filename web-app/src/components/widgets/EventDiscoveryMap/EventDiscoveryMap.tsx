import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMapsConfig } from "../../../api/maps";
import type { DiscoveryMapItem, DiscoveryViewport } from "../../../api/discovery";
import { errorText } from "../../../api/client";
import { useAsync } from "../../../hooks/useAsync";
import { currentCoordinates } from "../../../utils/geolocation";
import { discoveryViewport } from "../../../utils/discovery";
import { loadYandexMaps, locationCoordinates, reportMapError, type Coordinates, type MapInstance, type YandexMaps } from "../../../utils/yandexMaps";
import { Button, Notice } from "../../ui";

const CAMERA_KEY = "dvizh-discovery-camera-v1";
interface Camera { center: Coordinates; zoom: number }
function initialCamera(latitude?: string | null, longitude?: string | null): Camera {
    try {
        const stored = JSON.parse(sessionStorage.getItem(CAMERA_KEY) ?? "null") as Camera | null;
        if (stored && Array.isArray(stored.center) && stored.center.length === 2 && stored.center.every(Number.isFinite)
            && Math.abs(stored.center[0]) <= 180 && Math.abs(stored.center[1]) <= 90 && Number.isFinite(stored.zoom) && stored.zoom >= 0 && stored.zoom <= 23) return stored;
    } catch { /* Storage is optional, including in private browsing. */ }
    return { center: locationCoordinates(latitude ?? "", longitude ?? "") ?? [30.315868, 59.939095], zoom: 11 };
}

interface Props {
    items: DiscoveryMapItem[];
    total: number;
    loading: boolean;
    latitude?: string | null;
    longitude?: string | null;
    onViewport: (viewport: DiscoveryViewport) => void;
    onCluster: (item: DiscoveryMapItem) => void;
    onUnavailable: () => void;
}

export function EventDiscoveryMap({ items, total, loading, latitude, longitude, onViewport, onCluster, onUnavailable }: Props) {
    const navigate = useNavigate();
    const config = useAsync(getMapsConfig, "discovery-map-config");
    const container = useRef<HTMLDivElement>(null);
    const callbacks = useRef({ onViewport, onCluster, onUnavailable, navigate });
    useLayoutEffect(() => { callbacks.current = { onViewport, onCluster, onUnavailable, navigate }; });
    const [camera] = useState(() => initialCamera(latitude, longitude));
    const [instance, setInstance] = useState<{ map: MapInstance; api: YandexMaps } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [attempt, setAttempt] = useState(0);
    const [locating, setLocating] = useState(false);
    const [locationError, setLocationError] = useState<string | null>(null);
    const [collapsed, setCollapsed] = useState(false);
    const collapsedRef = useRef(collapsed);
    const contentId = useId();
    useLayoutEffect(() => { collapsedRef.current = collapsed; }, [collapsed]);
    const markers = useRef(new Map<string, { entity: InstanceType<YandexMaps["YMapMarker"]>; button: HTMLButtonElement; item: DiscoveryMapItem }>());
    const apiKey = config.data?.api_key;

    useEffect(() => {
        if (config.error !== undefined || config.data && !config.data.api_key) callbacks.current.onUnavailable();
    }, [config.error, config.data]);

    useEffect(() => {
        if (!apiKey) return;
        let cancelled = false;
        let map: MapInstance | undefined;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const activeMarkers = markers.current;
        let last = "";
        const publish = () => {
            if (collapsedRef.current) return;
            if (!map?.bounds || !map.center || map.zoom === undefined) return;
            const viewport = discoveryViewport(map.bounds, map.center, map.zoom);
            if (!viewport) return;
            const key = JSON.stringify(viewport);
            if (key === last) return;
            last = key;
            try { sessionStorage.setItem(CAMERA_KEY, JSON.stringify({ center: map.center, zoom: map.zoom })); } catch { /* Optional storage. */ }
            callbacks.current.onViewport(viewport);
        };
        loadYandexMaps(apiKey).then((api) => {
            if (cancelled || !container.current) return;
            map = new api.YMap(container.current, { location: camera });
            map.addChild(new api.YMapDefaultSchemeLayer({}));
            map.addChild(new api.YMapDefaultFeaturesLayer({}));
            map.addChild(new api.YMapListener({
                layer: "any",
                onUpdate: ({ mapInAction }) => {
                    if (timer) clearTimeout(timer);
                    if (!mapInAction) timer = setTimeout(publish, 300);
                },
                onResize: ({ mapInAction }) => { if (!mapInAction) { if (timer) clearTimeout(timer); timer = setTimeout(publish, 300); } },
            }));
            setInstance({ map, api });
            timer = setTimeout(publish, 0);
        }).catch((failure: unknown) => {
            if (!cancelled) {
                reportMapError("map_init", failure, apiKey);
                setError("Не удалось загрузить карту. Афиша работает без ограничения по области.");
                callbacks.current.onUnavailable();
            }
        });
        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
            activeMarkers.clear();
            map?.destroy();
        };
    }, [apiKey, camera, attempt]);

    useEffect(() => {
        if (!instance) return;
        const { map, api } = instance;
        // The server's complete representation is authoritative; never combine responses.
        const visible = items;
        const ids = new Set(visible.map((item) => item.id));
        for (const [id, marker] of markers.current) {
            if (!ids.has(id)) { map.removeChild(marker.entity); markers.current.delete(id); }
        }
        for (const item of visible) {
            let record = markers.current.get(item.id);
            if (!record) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "flex h-11 min-w-11 -translate-x-1/2 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border-2 border-white bg-bordermain px-2 text-buttons text-white shadow-lg outline-none focus-visible:ring-4 focus-visible:ring-borderfocus";
                const entity = new api.YMapMarker({ coordinates: [item.longitude, item.latitude] }, button);
                record = { button, entity, item };
                const active = record;
                button.onclick = (event) => {
                    event.stopPropagation();
                    if (active.item.type === "event" && active.item.event_id) callbacks.current.navigate(`/events/${active.item.event_id}`);
                    else callbacks.current.onCluster(active.item);
                };
                markers.current.set(item.id, record);
                map.addChild(entity);
            }
            record.item = item;
            record.entity.update({ coordinates: [item.longitude, item.latitude] });
            record.button.textContent = item.type === "cluster" ? String(item.count) : "●";
            const label = item.type === "cluster" ? `Показать мероприятия в группе: ${item.count}` : "Открыть мероприятие";
            record.button.setAttribute("aria-label", label);
            record.button.title = label;
            record.button.dataset.clusterId = item.id;
        }
    }, [instance, items]);

    const locate = async () => {
        if (!instance || locating) return;
        setLocating(true); setLocationError(null);
        try {
            const coordinates = await currentCoordinates();
            instance.map.update({ location: { center: coordinates, zoom: 12, duration: 300 } });
        } catch (failure) { setLocationError(errorText(failure)); }
        finally { setLocating(false); }
    };
    const unavailable = !config.loading && (!apiKey || config.error !== undefined);
    return <section className="flex min-w-0 flex-col gap-3 rounded-lg bg-background p-[10px]" aria-label="Мероприятия на карте">
        <div className="flex flex-wrap items-center justify-between gap-2 px-1">
            <h2 className="text-h2 text-textthird">Движ на карте</h2>
            <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => { setCollapsed(false); void locate(); }} disabled={!instance || locating}>{locating ? "Определяем…" : "Найди меня"}</Button>
                <Button onClick={() => setCollapsed((value) => !value)} ariaExpanded={!collapsed} ariaControls={contentId}>
                    {collapsed ? "Развернуть" : "Свернуть"}
                </Button>
            </div>
        </div>
        <div id={contentId} hidden={collapsed} className="space-y-3">
            {unavailable || error ? <Notice>{error ?? "Карта пока недоступна. Афиша работает без ограничения по области."}</Notice> : (
                <div className="relative overflow-hidden rounded-lg border-2 border-borderlight">
                    <div ref={container} className="h-[330px] w-full sm:h-[400px]" aria-label="Карта мероприятий Яндекса" />
                    {!instance && <div className="absolute inset-0 flex items-center justify-center bg-cards-surface p-4 text-center text-body text-textprimary" role="status">{error ?? "Загружаем карту…"}</div>}
                </div>
            )}
            {(error || config.error !== undefined) && <Button onClick={() => {
                setError(null); config.reload(); setAttempt((value) => value + 1);
            }}>Повторить загрузку карты</Button>}
            {!unavailable && !error && <p role="status" className="px-1 text-small text-textthird">
                {loading ? "Обновляем мероприятия в области…" : `Мероприятий в области: ${total}.`}
            </p>}
            {locationError && <Notice tone="error">{locationError}</Notice>}
        </div>
    </section>;
}
