import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getMapsConfig } from "../../../api/maps";
import { bootstrapDiscovery, type DiscoveryRequest, type DiscoveryMapItem, type DiscoveryViewport } from "../../../api/discovery";
import { errorText } from "../../../api/client";
import { useAsync } from "../../../hooks/useAsync";
import { currentCoordinates } from "../../../utils/geolocation";
import { discoveryViewport } from "../../../utils/discovery";
import { loadYandexMaps, reportMapError, type Coordinates, type MapInstance, type YandexMaps } from "../../../utils/yandexMaps";
import { initialDiscoveryCamera, type DiscoveryCamera } from "../../../utils/discoveryCamera";
import { mapMarkerPresentation } from "../../../utils/mapMarkers";
import { Button, Notice } from "../../ui";

const CAMERA_KEY = "dvizh-discovery-camera-v1";
// One automatic attempt per document, including remounts during SPA navigation.
let initialLocation: Promise<Coordinates> | undefined;
let initialCameraCommitted = false;
let lastUserLocation: Coordinates | null = null;
type Camera = DiscoveryCamera;
function initialCamera(): Camera {
    try {
        const stored = JSON.parse(sessionStorage.getItem(CAMERA_KEY) ?? "null") as Camera | null;
        if (stored && Array.isArray(stored.center) && stored.center.length === 2 && stored.center.every(Number.isFinite)
            && Math.abs(stored.center[0]) <= 180 && Math.abs(stored.center[1]) <= 90 && Number.isFinite(stored.zoom) && stored.zoom >= 0 && stored.zoom <= 23) return stored;
    } catch { /* Storage is optional, including in private browsing. */ }
    return { center: [30.315868, 59.939095], zoom: 11 };
}

interface Props {
    initialFilters: DiscoveryRequest["filters"] | null;
    queryFailed: boolean;
    items: DiscoveryMapItem[];
    total: number;
    loading: boolean;
    mapViewport: DiscoveryViewport | null;
    collapsed: boolean;
    onCollapsedChange: (collapsed: boolean) => void;
    onViewport: (viewport: DiscoveryViewport) => void;
    onCluster: (item: DiscoveryMapItem) => void;
    onUnavailable: () => void;
}

export function EventDiscoveryMap({ initialFilters, queryFailed, items, total, loading, mapViewport, collapsed, onCollapsedChange, onViewport, onCluster, onUnavailable }: Props) {
    const navigate = useNavigate();
    const config = useAsync(getMapsConfig, "discovery-map-config");
    const container = useRef<HTMLDivElement>(null);
    const callbacks = useRef({ onViewport, onCluster, onUnavailable, navigate });
    useLayoutEffect(() => { callbacks.current = { onViewport, onCluster, onUnavailable, navigate }; });
    const [camera, setCamera] = useState<Camera | null>(() => initialCameraCommitted ? initialCamera() : null);
    const filtersKey = initialFilters === null ? null : JSON.stringify(initialFilters);
    const [revealed, setRevealed] = useState(false);
    const [instance, setInstance] = useState<{ map: MapInstance; api: YandexMaps } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [attempt, setAttempt] = useState(0);
    const [locating, setLocating] = useState(false);
    const [locationError, setLocationError] = useState<string | null>(null);
    const [locationTarget, setLocationTarget] = useState<Coordinates | null>(null);
    const [userLocation, setUserLocation] = useState<Coordinates | null>(() => lastUserLocation);
    const locationRequest = useRef(0);
    const appliedLocation = useRef<{ map: MapInstance; coordinates: Coordinates } | null>(null);
    const collapsedRef = useRef(collapsed);
    const contentId = useId();
    const publishViewport = useRef<() => void>(() => {});
    useLayoutEffect(() => { collapsedRef.current = collapsed; }, [collapsed]);
    const markers = useRef(new Map<string, { entity: InstanceType<YandexMaps["YMapMarker"]>; button: HTMLButtonElement; item: DiscoveryMapItem }>());
    const apiKey = config.data?.api_key;
    const locate = useCallback(async () => {
        const request = ++locationRequest.current;
        setLocating(true); setLocationError(null);
        try {
            const coordinates = await currentCoordinates();
            if (request === locationRequest.current) { lastUserLocation = coordinates; setLocationTarget(coordinates); setUserLocation(coordinates); }
        } catch (failure) {
            if (request === locationRequest.current) setLocationError(errorText(failure));
        } finally {
            if (request === locationRequest.current) setLocating(false);
        }
    }, []);

    const cancelLocation = useCallback(() => { locationRequest.current++; }, []);

    useEffect(() => cancelLocation, [cancelLocation]);

    useEffect(() => {
        if (camera || !apiKey || filtersKey === null) return;
        const controller = new AbortController();
        const initialize = async () => {
            if (controller.signal.aborted) return;
            setLocating(true);
            let next = initialCamera();
            let coordinates: Coordinates | null = null;
            try {
                initialLocation ??= currentCoordinates();
                coordinates = await initialLocation;
            } catch (failure) {
                if (!controller.signal.aborted) setLocationError(errorText(failure));
            }
            if (controller.signal.aborted) return;
            if (coordinates) {
                lastUserLocation = coordinates;
                setUserLocation(coordinates);
                const size = container.current?.getBoundingClientRect();
                next = initialDiscoveryCamera(coordinates, null, size?.width ?? 600, size?.height ?? 400);
                try {
                    const result = await bootstrapDiscovery(JSON.parse(filtersKey), {
                        longitude: coordinates[0], latitude: coordinates[1],
                    }, AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]));
                    const point = result.nearest?.point;
                    if (point && (!Number.isFinite(point.longitude) || Math.abs(point.longitude) > 180
                        || !Number.isFinite(point.latitude) || Math.abs(point.latitude) > 90)) throw new Error("Некорректная точка события.");
                    const currentSize = container.current?.getBoundingClientRect();
                    next = initialDiscoveryCamera(coordinates, point ? [point.longitude, point.latitude] : null,
                        currentSize?.width ?? 600, currentSize?.height ?? 400);
                } catch {
                    if (!controller.signal.aborted) setLocationError("Не удалось найти ближайшее событие. Показываем область рядом с вами.");
                }
            }
            if (!controller.signal.aborted) {
                initialCameraCommitted = true;
                try { sessionStorage.setItem(CAMERA_KEY, JSON.stringify(next)); } catch { /* Optional storage. */ }
                setCamera(next);
                setLocating(false);
            }
        };
        void Promise.resolve().then(initialize);
        return () => controller.abort();
    }, [apiKey, filtersKey, camera]);

    useEffect(() => {
        if (!instance || revealed || loading) return;
        const current = instance.map;
        const matches = mapViewport && current.center && current.zoom !== undefined
            && Math.abs(current.zoom - mapViewport.zoom) < 0.02
            && Math.abs(current.center[0] - mapViewport.center.longitude) < 0.00001
            && Math.abs(current.center[1] - mapViewport.center.latitude) < 0.00001;
        if (matches || queryFailed) void Promise.resolve().then(() => setRevealed(true));
    }, [instance, revealed, loading, mapViewport, queryFailed]);
    useEffect(() => {
        if (!instance || !locationTarget || collapsed) return;
        if (appliedLocation.current?.map === instance.map
            && appliedLocation.current.coordinates === locationTarget) return;
        appliedLocation.current = { map: instance.map, coordinates: locationTarget };
        instance.map.update({ location: { center: locationTarget, zoom: 12, duration: 300 } });
    }, [instance, locationTarget, collapsed]);

    useEffect(() => {
        if (config.error !== undefined || config.data && !config.data.api_key) callbacks.current.onUnavailable();
    }, [config.error, config.data]);

    useEffect(() => {
        if (!collapsed && instance) publishViewport.current();
    }, [collapsed, instance]);

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
        publishViewport.current = publish;
        loadYandexMaps(apiKey).then((api) => {
            if (cancelled || !container.current || !camera) return;
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
        if (!instance || !userLocation) return;
        const dot = document.createElement("span");
        dot.setAttribute("role", "img");
        dot.setAttribute("aria-label", "Ваше местоположение");
        dot.className = "pointer-events-none block h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-white bg-blue-600 shadow-[0_0_0_5px_rgba(37,99,235,0.2)]";
        const marker = new instance.api.YMapMarker({ coordinates: userLocation, zIndex: 1000 }, dot);
        instance.map.addChild(marker);
        return () => { instance.map.removeChild(marker); };
    }, [instance, userLocation]);

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
            const presentation = mapMarkerPresentation(item);
            record.button.className = `flex h-11 min-w-11 -translate-x-1/2 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full border-2 border-white px-2 text-buttons shadow-lg outline-none focus-visible:ring-4 focus-visible:ring-borderfocus ${presentation.classes}`;
            record.button.setAttribute("aria-label", presentation.tooltip.replace("\n", ". "));
            record.button.title = presentation.tooltip;
            record.button.dataset.clusterId = item.id;
        }
    }, [instance, items]);

    const unavailable = !config.loading && (!apiKey || config.error !== undefined);
    return <section className="flex min-w-0 cursor-pointer flex-col rounded-lg bg-background p-[10px]" aria-label="Мероприятия на карте"
        onClick={(event) => {
            if (!(event.target instanceof Element)
                || event.target.closest("button, a, input, select, textarea, [data-map-surface]")) return;
            onCollapsedChange(!collapsed);
        }}>
        <div className="flex flex-wrap items-center justify-between gap-2 px-1">
            <h2 className="text-h2 text-textthird">Движ на карте</h2>
            <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => {
                    if (collapsed) onCollapsedChange(false);
                    void locate();
                }} disabled={!instance || locating}>{locating ? "Определяем…" : "Найди меня"}</Button>
                <Button onClick={() => onCollapsedChange(!collapsed)} ariaExpanded={!collapsed} ariaControls={contentId}>
                    {collapsed ? "Развернуть" : "Свернуть"}
                </Button>
            </div>
        </div>
        <div id={contentId} aria-hidden={collapsed} inert={collapsed}
            className={`grid transition-[grid-template-rows,opacity,padding-top] duration-300 ease-in-out motion-reduce:transition-none ${collapsed ? "grid-rows-[0fr] pt-0 opacity-0" : "grid-rows-[1fr] pt-3 opacity-100"}`}>
            <div className="min-h-0 overflow-hidden">
            <div className="space-y-3">
            {unavailable || error ? <Notice>{error ?? "Карта пока недоступна. Афиша работает без ограничения по области."}</Notice> : (
                <div data-map-surface className="relative cursor-auto overflow-hidden rounded-lg border-2 border-borderlight">
                    <div ref={container} inert={!revealed} aria-hidden={!revealed} className="h-[330px] w-full sm:h-[400px]" aria-label="Карта мероприятий Яндекса" />
                    {!revealed && <div className="absolute inset-0 flex items-center justify-center bg-cards-surface p-4 text-center text-body text-textprimary" role="status">{error ?? "Загружаем карту…"}</div>}
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
            </div>
        </div>
    </section>;
}
