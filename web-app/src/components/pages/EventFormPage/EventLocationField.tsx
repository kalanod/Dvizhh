import { useEffect, useId, useRef, useState } from "react";
import { errorText } from "../../../api/client";
import { geocodeAddress, getMapsConfig, suggestAddresses, type AddressSuggestion } from "../../../api/maps";
import { useAsync } from "../../../hooks/useAsync";
import { locationCoordinates, type Coordinates } from "../../../utils/yandexMaps";
import { Button, FormField, Input, Notice } from "../../ui";
import { YandexMap } from "../../widgets/EventLocation/YandexMap";
import type { EventFormState } from "./formState";

type LocationFields = Pick<EventFormState, "address" | "city" | "latitude" | "longitude">;

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
    const geocoding = useRef<AbortController | null>(null);
    const listId = useId();
    const searchEnabled = Boolean(config.data?.search_enabled);
    const searchKey = `${value.city}:${value.address}`;
    const canSuggest = open && searchEnabled && value.address.trim().length >= 3;
    const current = suggestions?.key === searchKey ? suggestions : null;
    const items = canSuggest ? current?.items ?? [] : [];

    useEffect(() => {
        if (!canSuggest) return;
        const controller = new AbortController();
        const timer = setTimeout(() => {
            suggestAddresses(value.address, value.city, controller.signal).then(
                (items) => { if (!controller.signal.aborted) setSuggestions({ key: searchKey, items }); },
                (err: unknown) => { if (!controller.signal.aborted) setSuggestions({ key: searchKey, items: [], error: errorText(err) }); },
            );
        }, 350);
        return () => { clearTimeout(timer); controller.abort(); };
    }, [canSuggest, searchKey, value.address, value.city]);

    useEffect(() => () => geocoding.current?.abort(), []);

    const editAddress = (address: string) => {
        geocoding.current?.abort();
        setResolving(false);
        setError(null);
        setActive(-1);
        setOpen(true);
        onChange({ address, latitude: "", longitude: "" });
    };

    const resolve = async (suggestion?: AddressSuggestion, point?: Coordinates) => {
        geocoding.current?.abort();
        const controller = new AbortController();
        geocoding.current = controller;
        setOpen(false);
        setError(null);
        setResolving(true);
        if (point) {
            onChange({ latitude: point[1].toFixed(6), longitude: point[0].toFixed(6), address: "" });
        } else {
            onChange({ address: suggestion?.address ?? value.address, latitude: "", longitude: "" });
        }
        try {
            const query = point ? point.join(",") : suggestion?.address ?? [value.city, value.address].filter(Boolean).join(", ");
            const place = await geocodeAddress(query, suggestion?.uri, controller.signal);
            if (controller.signal.aborted) return;
            onChange({
                address: place.address_line,
                city: place.city ?? value.city,
                latitude: (point?.[1] ?? Number(place.latitude)).toFixed(6),
                longitude: (point?.[0] ?? Number(place.longitude)).toFixed(6),
            });
        } catch (err) {
            if (!controller.signal.aborted) setError(errorText(err));
        } finally {
            if (!controller.signal.aborted) setResolving(false);
        }
    };

    return (
        <div className="flex min-w-0 flex-col gap-3">
            <div className="relative" onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
            }}>
                <FormField label="Адрес" htmlFor="event-address" hint="Начните вводить адрес или выберите точку на карте">
                    <div className="flex items-start gap-2">
                        <Input
                            id="event-address"
                            role="combobox"
                            aria-autocomplete="list"
                            aria-expanded={items.length > 0}
                            aria-controls={listId}
                            aria-activedescendant={active >= 0 && active < items.length ? `${listId}-${active}` : undefined}
                            autoComplete="off"
                            placeholder="Невский проспект, 1"
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
                                    if (searchEnabled && value.address.trim()) void resolve(items[active]);
                                }
                            }}
                        />
                        <Button disabled={disabled || resolving || !searchEnabled || !value.address.trim()} onClick={() => void resolve()}>
                            Найти
                        </Button>
                    </div>
                </FormField>
                {items.length > 0 && (
                    <ul id={listId} role="listbox" aria-label="Подсказки адресов" className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border-2 border-borderlight bg-primary shadow-lg">
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
                                    <span>{item.title}</span>
                                    {item.subtitle && <span className="text-small text-textsecondary">{item.subtitle}</span>}
                                </button>
                            </li>
                        ))}
                        <li role="presentation" className="px-4 py-2 text-small text-textsecondary">Подсказки Яндекс Карт</li>
                    </ul>
                )}
            </div>
            <div role="status" className="text-small text-textsecondary">
                {resolving ? "Определяем адрес…" : canSuggest && !current ? "Ищем адреса…" : canSuggest && current && !items.length && !current.error ? "Подсказок нет. Уточните адрес или выберите точку на карте." : ""}
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
