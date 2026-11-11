import { getMapsConfig } from "../../../api/maps";
import { errorText } from "../../../api/client";
import { useAsync } from "../../../hooks/useAsync";
import type { EventLocation } from "../../../models/event";
import { YandexMap } from "./YandexMap";

export const EventLocationMap = ({ location }: { location: EventLocation }) => {
    const config = useAsync(getMapsConfig, "yandex-maps-config");
    if (location.latitude === null || location.longitude === null) return null;
    if (config.loading) return <p className="text-small text-textsecondary">Загружаем карту…</p>;
    if (config.error || !config.data?.api_key) {
        return <p className="text-small text-textsecondary">{config.error ? errorText(config.error) : "Карта пока недоступна."}</p>;
    }
    return <YandexMap apiKey={config.data.api_key} latitude={location.latitude} longitude={location.longitude} />;
};
