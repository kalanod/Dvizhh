import type { DvizhEvent, EventFormat, EventInput, EventJoinPolicy, EventVisibility } from "../../../models";
import { browserTimeZone, fromDateTimeLocal, toDateTimeLocal } from "../../../utils/format";

/** Состояние формы: все поля строками, как их отдают input-ы. */
export interface EventFormState {
    title: string;
    description: string;
    tags: string;
    startsAt: string;
    endsAt: string;
    isAllDay: boolean;
    timezone: string;
    format: EventFormat;
    placeName: string;
    city: string;
    address: string;
    latitude: string;
    longitude: string;
    onlineUrl: string;
    registrationUrl: string;
    priceMin: string;
    priceMax: string;
    capacity: string;
    visibility: EventVisibility;
    joinPolicy: EventJoinPolicy;
}

// Центр Санкт-Петербурга: координаты места обязательны в API, пока нет выбора на карте.
const DEFAULT_COORDS = { latitude: "59.939095", longitude: "30.315868" };

export const emptyForm = (): EventFormState => ({
    title: "",
    description: "",
    tags: "",
    startsAt: "",
    endsAt: "",
    isAllDay: false,
    timezone: browserTimeZone(),
    format: "OFFLINE",
    placeName: "",
    city: "",
    address: "",
    ...DEFAULT_COORDS,
    onlineUrl: "",
    registrationUrl: "",
    priceMin: "",
    priceMax: "",
    capacity: "",
    visibility: "PUBLIC",
    joinPolicy: "OPEN",
});

export const formFromEvent = (event: DvizhEvent): EventFormState => ({
    title: event.title,
    description: event.description,
    tags: event.tags.join(", "),
    startsAt: toDateTimeLocal(event.starts_at),
    endsAt: toDateTimeLocal(event.ends_at),
    isAllDay: event.is_all_day,
    timezone: event.timezone,
    format: event.format,
    placeName: event.location?.name ?? "",
    city: event.location?.city ?? "",
    address: event.location?.address_line ?? "",
    latitude: event.location?.latitude ?? DEFAULT_COORDS.latitude,
    longitude: event.location?.longitude ?? DEFAULT_COORDS.longitude,
    onlineUrl: event.online_url ?? "",
    registrationUrl: event.registration_url ?? "",
    priceMin: event.price_min ?? "",
    priceMax: event.price_max ?? "",
    capacity: event.capacity?.toString() ?? "",
    visibility: event.visibility,
    joinPolicy: event.join_policy,
});

const orNull = (value: string) => value.trim() || null;

const coordinate = (value: string) => {
    const number = Number(value.replace(",", "."));
    return Number.isFinite(number) ? number.toFixed(6) : value;
};

const money = (value: string) => {
    const trimmed = value.trim().replace(",", ".");
    return trimmed === "" ? null : trimmed;
};

/** Проверки, которые удобнее показать до отправки; остальное валидирует backend. */
export const validateForm = (form: EventFormState): string | null => {
    if (!form.title.trim()) return "Укажите название.";
    if (!form.startsAt) return "Укажите, когда начинается событие.";
    if (form.endsAt && form.endsAt <= form.startsAt) return "Окончание должно быть позже начала.";
    if (form.format !== "ONLINE" && (!form.latitude.trim() || !form.longitude.trim())) {
        return "Для офлайн-события нужны координаты места.";
    }
    if (form.format !== "OFFLINE" && !form.onlineUrl.trim()) return "Добавьте ссылку на трансляцию.";
    if (form.priceMax.trim() && !form.priceMin.trim()) return "Укажите цену «от», если задаёте цену «до».";
    return null;
};

export const formToInput = (form: EventFormState): EventInput => {
    const capacity = form.capacity.trim() === "" ? null : Number(form.capacity);
    const priceMin = money(form.priceMin);

    return {
        title: form.title.trim(),
        description: form.description.trim(),
        tags: form.tags
            .split(",")
            .map((tag) => tag.trim().replace(/^#/, ""))
            .filter(Boolean),
        starts_at: fromDateTimeLocal(form.startsAt) ?? "",
        ends_at: fromDateTimeLocal(form.endsAt),
        timezone: form.timezone,
        is_all_day: form.isAllDay,
        format: form.format,
        location:
            form.format === "ONLINE"
                ? null
                : {
                      name: orNull(form.placeName),
                      city: orNull(form.city),
                      address_line: orNull(form.address),
                      latitude: coordinate(form.latitude),
                      longitude: coordinate(form.longitude),
                  },
        online_url: form.format === "OFFLINE" ? null : orNull(form.onlineUrl),
        registration_url: orNull(form.registrationUrl),
        price_min: priceMin,
        price_max: priceMin ? money(form.priceMax) : null,
        currency: "RUB",
        capacity: capacity !== null && Number.isFinite(capacity) ? capacity : null,
        visibility: form.visibility,
        join_policy: form.joinPolicy,
    };
};
