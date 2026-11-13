import type { DvizhEvent, EventFormat, EventInput, EventJoinPolicy, EventTag, EventVisibility } from "../../../models";
import { MAX_EVENT_TAGS } from "../../../utils/tags";
import { browserTimeZone, fromDateTimeLocal, toDateTimeLocal } from "../../../utils/format";

/** Состояние формы: все поля строками, как их отдают input-ы. */
export interface EventFormState {
    title: string;
    description: string;
    tags: EventTag[];
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
    currency: string;
    priceMin: string;
    priceMax: string;
    capacity: string;
    visibility: EventVisibility;
    joinPolicy: EventJoinPolicy;
}

export const emptyForm = (): EventFormState => ({
    title: "",
    description: "",
    tags: [],
    startsAt: "",
    endsAt: "",
    isAllDay: false,
    timezone: browserTimeZone(),
    format: "OFFLINE",
    placeName: "",
    city: "",
    address: "",
    latitude: "",
    longitude: "",
    onlineUrl: "",
    registrationUrl: "",
    currency: "RUB",
    priceMin: "",
    priceMax: "",
    capacity: "",
    visibility: "PUBLIC",
    joinPolicy: "OPEN",
});

export const formFromEvent = (event: DvizhEvent): EventFormState => ({
    title: event.title,
    description: event.description,
    tags: event.tags ?? [],
    startsAt: toDateTimeLocal(event.starts_at, event.timezone),
    endsAt: toDateTimeLocal(event.ends_at, event.timezone),
    isAllDay: event.is_all_day,
    timezone: event.timezone,
    format: event.format,
    placeName: event.location?.name ?? "",
    city: event.location?.city ?? "",
    address: event.location?.address_line ?? "",
    latitude: event.location?.latitude ?? "",
    longitude: event.location?.longitude ?? "",
    onlineUrl: event.online_url ?? "",
    registrationUrl: event.registration_url ?? "",
    currency: event.currency ?? "RUB",
    priceMin: event.price_min ?? "",
    priceMax: event.price_max ?? "",
    capacity: event.capacity?.toString() ?? "",
    visibility: event.visibility,
    joinPolicy: event.join_policy,
});

const orNull = (value: string) => value.trim() || null;

const coordinate = (value: string) => {
    if (!value.trim()) return null;
    const number = Number(value.replace(",", "."));
    return Number.isFinite(number) ? number.toFixed(6) : value;
};

const money = (value: string) => {
    const trimmed = value.trim().replace(",", ".");
    return trimmed === "" ? null : trimmed;
};

/** Проверки, которые удобнее показать до отправки; остальное валидирует backend. */
export const validateForm = (form: EventFormState): string | null => {
    if (new Set(form.tags.map((tag) => tag.id)).size > MAX_EVENT_TAGS) return "Можно выбрать не больше пяти тегов.";
    if (!/^[A-Z]{3}$/.test(form.currency)) return "Укажите трёхбуквенный код валюты.";
    try {
        new Intl.DateTimeFormat("en", { timeZone: form.timezone }).format();
        fromDateTimeLocal(form.startsAt, form.timezone);
        fromDateTimeLocal(form.endsAt, form.timezone);
    } catch { return "Проверьте часовой пояс и время: выбранное время может не существовать при переходе на летнее время."; }
    if (!form.title.trim()) return "Укажите название.";
    if (!form.startsAt) return "Укажите, когда начинается событие.";
    if (form.endsAt && form.endsAt <= form.startsAt) return "Окончание должно быть позже начала.";
    if (form.format !== "ONLINE" && !form.address.trim() && (!form.latitude.trim() || !form.longitude.trim())) {
        return "Укажите адрес или выберите место события на карте.";
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
        tag_ids: [...new Set(form.tags.map((tag) => tag.id))],
        starts_at: fromDateTimeLocal(form.startsAt, form.timezone) ?? "",
        ends_at: fromDateTimeLocal(form.endsAt, form.timezone),
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
        currency: form.currency,
        capacity: capacity !== null && Number.isFinite(capacity) ? capacity : null,
        visibility: form.visibility,
        join_policy: form.joinPolicy,
    };
};
