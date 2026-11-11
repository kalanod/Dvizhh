import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { errorText } from "../../../api/client";
import { loadYandexMaps, locationCoordinates, reportMapError, type Coordinates, type MapInstance, type YandexMaps } from "../../../utils/yandexMaps";

interface YandexMapProps {
    apiKey: string;
    latitude: string;
    longitude: string;
    onPointChange?: (point: Coordinates) => void;
}

export const YandexMap = ({ apiKey, latitude, longitude, onPointChange }: YandexMapProps) => {
    const container = useRef<HTMLDivElement>(null);
    const callback = useRef(onPointChange);
    const marker = useRef<InstanceType<YandexMaps["YMapMarker"]> | null>(null);
    const [instance, setInstance] = useState<{ map: MapInstance; api: YandexMaps } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const editable = Boolean(onPointChange);

    useLayoutEffect(() => { callback.current = onPointChange; });

    useEffect(() => {
        let cancelled = false;
        let map: MapInstance | undefined;
        loadYandexMaps(apiKey).then((api) => {
            if (cancelled || !container.current) return;
            map = new api.YMap(container.current, {
                location: { center: [30.315868, 59.939095], zoom: 10 },
            });
            map.addChild(new api.YMapDefaultSchemeLayer({}));
            map.addChild(new api.YMapDefaultFeaturesLayer({}));
            map.addChild(new api.YMapListener({
                layer: "any",
                onClick: (object, event) => {
                    if (object?.type !== "marker") callback.current?.(event.coordinates);
                },
            }));
            setInstance({ map, api });
        }).catch((err: unknown) => {
            if (!cancelled) {
                reportMapError("map_init", err, apiKey);
                setError(errorText(err));
            }
        });
        return () => {
            cancelled = true;
            marker.current = null;
            map?.destroy();
        };
    }, [apiKey]);

    useEffect(() => {
        if (!instance) return;
        const { map, api } = instance;
        if (marker.current) {
            map.removeChild(marker.current);
            marker.current = null;
        }
        const coordinates = locationCoordinates(latitude, longitude);
        if (!coordinates) return;
        const pin = document.createElement("div");
        pin.setAttribute("aria-label", "Место события");
        pin.style.cssText = "width:28px;height:36px;margin-left:-14px;margin-top:-36px;cursor:inherit";
        pin.innerHTML = '<svg width="28" height="36" viewBox="0 0 28 36" xmlns="http://www.w3.org/2000/svg"><path d="M14 35S1 23 1 14a13 13 0 0 1 26 0c0 9-13 21-13 21Z" fill="#c1274b" stroke="white" stroke-width="2"/><circle cx="14" cy="14" r="5" fill="white"/></svg>';
        marker.current = new api.YMapMarker({
            coordinates,
            draggable: editable,
            onDragEnd: (point: Coordinates) => callback.current?.(point),
        }, pin);
        map.addChild(marker.current);
        map.update({ location: { center: coordinates, zoom: 16, duration: 250 } });
    }, [instance, latitude, longitude, editable]);

    const point = locationCoordinates(latitude, longitude);
    const link = point
        ? `https://yandex.ru/maps/?pt=${point.join(",")}&z=16&l=map`
        : "https://yandex.ru/maps/";

    return (
        <div className="flex w-full min-w-0 flex-col gap-2">
            <div className="relative overflow-hidden rounded-lg border-2 border-borderlight">
                <div ref={container} className="h-[320px] w-full sm:h-[380px]" aria-label="Яндекс Карты: место события" />
                {!instance && (
                    <div className="absolute inset-0 flex items-center justify-center bg-primary p-4 text-center text-body text-textsecondary" role="status">
                        {error ?? "Загружаем карту…"}
                    </div>
                )}
            </div>
            <a href={link} target="_blank" rel="noreferrer" className="self-start text-small text-textghost hover:underline">
                Открыть в Картах
            </a>
        </div>
    );
};
