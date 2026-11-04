import { useEffect, useId, useRef, useState } from "react";
import { errorText } from "../../../api/client";
import { geocodeAddress, getMapsConfig, suggestAddresses, type AddressSuggestion } from "../../../api/maps";
import { useAsync } from "../../../hooks/useAsync";
import { locationCoordinates, type Coordinates } from "../../../utils/yandexMaps";
import { currentCoordinates } from "../../../utils/geolocation";
import { Button, FormField, Input, Notice } from "../../ui";
import { YandexMap } from "../../widgets/EventLocation/YandexMap";
import type { EventFormState } from "./formState";

type LocationFields = Pick<EventFormState, "address" | "city" | "latitude" | "longitude" | "placeName">;

interface Props {
    value: LocationFields;
    disabled: boolean;
    onChange: (value: Partial<LocationFields>) => void;
}

export const EventLocationField = ({ value, disabled, onChange }: Props) => {
    const config = useAsync(getMapsConfig, "yandex-maps-config");
    const [open, setOpen] = useState(false);
    const [active, setActive] = useState(-1);
    const [suggestions, setSuggestions] = useState<{ key: string; items: AddressSuggestion[]; error?: string } | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [resolving, setResolving] = useState(false);
    const [locating, setLocating] = useState(false);
    const [userPoint, setUserPoint] = useState<Coordinates | null>(null);
    const [selectedPoint, setSelectedPoint] = useState(() => locationCoordinates(value.latitude, value.longitude));
    const center = userPoint ?? selectedPoint;
    const centerLongitude = center?.[0];
    const centerLatitude = center?.[1];
    const locationRequest = useRef<AbortController | null>(null);
    const geocoding = useRef<AbortController | null>(null);
    const listId = useId();
    const searchEnabled = Boolean(config.data?.search_enabled);
    const searchKey = `${value.city}:${value.address}:${centerLongitude}:${centerLatitude}`;
    const canSuggest = open && searchEnabled && value.address.trim().length >= 3;
    const current = suggestions?.key === searchKey ? suggestions : null;
    const items = canSuggest ? current?.items ?? [] : [];

    useEffect(() => {
        if (!canSuggest) return;
        const controller = new AbortController();
        const timer = setTimeout(() => {
            suggestAddresses(value.address, value.city, controller.signal,
                centerLongitude !== undefined && centerLatitude !== undefined ? [centerLongitude, centerLatitude] : null).then(
                (items) => { if (!controller.signal.aborted) setSuggestions({ key: searchKey, items }); },
                (err: unknown) => { if (!controller.signal.aborted) setSuggestions({ key: searchKey, items: [], error: errorText(err) }); },
            );
        }, 350);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [canSuggest, searchKey, value.address, value.city, centerLongitude, centerLatitude]);

    useEffect(() => () => {
        geocoding.current?.abort();
        locationRequest.current?.abort();
    }, []);

    const editAddress = (address: string) => {
        locationRequest.current?.abort();
        setLocating(false);
        geocoding.current?.abort();
        setResolving(false);
        setError(null);
        setActive(-1);
        setOpen(true);
        onChange({ address, latitude: "", longitude: "" });
    };

    const resolve = async (suggestion?: AddressSuggestion, point?: Coordinates) => {
        locationRequest.current?.abort();
        setLocating(false);
        geocoding.current?.abort();
        const controller = new AbortController();
        geocoding.current = controller;
        setOpen(false);
        setError(null);
        setResolving(true);
        if (point) {
            setSelectedPoint(point);
            onChange({ latitude: point[1].toFixed(6), longitude: point[0].toFixed(6), address: "" });
        } else {
            onChange({ address: suggestion?.address ?? value.address, latitude: "", longitude: "" });
        }
        try {
            const query = point ? point.join(",") : suggestion?.address ?? [value.city, value.address].filter(Boolean).join(", ");
            const place = await geocodeAddress(query, suggestion?.uri, controller.signal);
            if (controller.signal.aborted) return;
            setSelectedPoint(point ?? [Number(place.longitude), Number(place.latitude)]);
            onChange({
                ...(place.name ? { placeName: place.name } : {}),
                address: place.address_line,
                city: place.city ?? suggestion?.city ?? value.city,
                latitude: (point?.[1] ?? Number(place.latitude)).toFixed(6),
                longitude: (point?.[0] ?? Number(place.longitude)).toFixed(6),
            });
        } catch (err) {
            if (!controller.signal.aborted) setError(errorText(err));
        } finally {
            if (!controller.signal.aborted) setResolving(false);
        }
    };

    const locate = async () => {
        locationRequest.current?.abort();
        geocoding.current?.abort();
        const controller = new AbortController();
        locationRequest.current = controller;
        setOpen(false);
        setError(null);
        setResolving(false);
        setLocating(true);
        try {
            const point = await currentCoordinates();
            if (!controller.signal.aborted) {
                setUserPoint(point);
                await resolve(undefined, point);
            }
        } catch (err) {
            if (!controller.signal.aborted) setError(errorText(err));
        } finally {
            if (!controller.signal.aborted) setLocating(false);
        }
    };

    return (
        <div className="flex min-w-0 flex-col gap-3">
            <div className="relative" onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
            }}>
                <FormField label="Адрес или заведение" htmlFor="event-address" hint="Введите адрес, название или тип места — например, «антикафе»">
                    <div className="flex items-start gap-2">
                        <Input
                            id="event-address"
                            role="combobox"
                            aria-autocomplete="list"
                            aria-expanded={items.length > 0}
                            aria-controls={listId}
                            aria-activedescendant={active >= 0 && active < items.length ? `${listId}-${active}` : undefined}
                            autoComplete="off"
                            placeholder="Антикафе, кофейня или Невский проспект, 1"
                            value={value.address}
                            onChange={editAddress}
                            onFocus={() => { if (!value.latitude) setOpen(true); }}
                            onKeyDown={(event) => {
                                if (event.key === "ArrowDown" && items.length) {
                                    event.preventDefault();
                                    setActive((index) => (index + 1) % items.length);
                                } else if (event.key === "ArrowUp" && items.length) {
                                    event.preventDefault();
                                    setActive((index) => (index + items.length - 1) % items.length);
                                } else if (event.key === "Escape") {
                                    setOpen(false);
                                } else if (event.key === "Enter") {
                                    event.preventDefault();
                                    if (searchEnabled && value.address.trim()) {
                                        if (active >= 0) void resolve(items[active]);
                                        else setOpen(true);
                                    }
                                }
                            }}
                        />
                        <Button disabled={disabled || resolving || !searchEnabled || !value.address.trim()} onClick={() => { setOpen(true); setActive(-1); }}>
                            Найти
                        </Button>
                    </div>
                </FormField>
                {items.length > 0 && (
                    <ul id={listId} role="listbox" aria-label="Адреса и заведения" className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border-2 border-borderlight bg-primary shadow-lg">
                        {items.map((item, index) => (
                            <li key={`${item.uri}:${index}`} role="presentation">
                                <button
                                    id={`${listId}-${index}`}
                                    type="button"
                                    role="option"
                                    aria-selected={index === active}
                                    className={`flex w-full flex-col px-4 py-3 text-left text-body text-textprimary hover:bg-secondary ${index === active ? "bg-secondary" : ""}`}
                                    onMouseDown={(event) => event.preventDefault()}
                                    onClick={() => void resolve(item)}
                                >
                                    <span>{item.title}{item.kind === "biz" ? " · Заведение" : ""}</span>
                                    {item.subtitle && <span className="text-small text-textsecondary">{item.subtitle}</span>}
                                </button>
                            </li>
                        ))}
                        <li role="presentation" className="px-4 py-2 text-small text-textsecondary">Подсказки Яндекс Карт</li>
                    </ul>
                )}
            </div>
            <Button disabled={disabled || locating || resolving || !config.data?.api_key} onClick={() => void locate()}>
                {locating ? "Определяем местоположение…" : "Моё местоположение"}
            </Button>
            <p className="text-small text-textsecondary">
                {userPoint ? "Приоритет — места рядом с вами." : selectedPoint ? "Приоритет — места рядом с выбранной точкой." : "Для поиска поблизости нажмите «Моё местоположение». Пока поиск учитывает указанный город."}
            </p>
            <div role="status" className="text-small text-textsecondary">
                {locating ? "Разрешите доступ к местоположению, если браузер запросит его." : resolving ? "Определяем адрес…" : canSuggest && !current ? "Ищем адреса…" : canSuggest && current && !items.length && !current.error ? "Подсказок нет. Уточните адрес или выберите точку на карте." : ""}
            </div>
            {(error || (canSuggest && current?.error)) && <Notice tone="error">{error ?? current?.error}</Notice>}
            {config.data?.api_key ? (
                <YandexMap
                    apiKey={config.data.api_key}
                    latitude={value.latitude}
                    longitude={value.longitude}
                    onPointChange={disabled ? undefined : (point) => void resolve(undefined, point)}
                />
            ) : (
                <p className="rounded-lg border-2 border-borderlight p-4 text-body text-textsecondary">
                    {config.loading ? "Загружаем карту…" : config.error ? errorText(config.error) : "Карта пока не настроена."}
                </p>
            )}
            {config.data?.api_key && !searchEnabled && <p className="text-small text-textsecondary">Подсказки адресов пока недоступны. Место можно выбрать на карте.</p>}
            {locationCoordinates(value.latitude, value.longitude) && (
                <span className="text-small text-textsecondary">Место выбрано. Метку можно переместить, чтобы уточнить вход.</span>
            )}
        </div>
    );
};
