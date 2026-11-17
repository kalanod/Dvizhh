import type { DvizhEvent, EventFormat, EventInput, EventJoinPolicy, EventTag, EventVisibility } from "../../../models";
import { MAX_EVENT_TAGS } from "../../../utils/tags";
import { browserTimeZone, fromDateTimeLocal, toDateTimeLocal } from "../../../utils/format";
import { placeCoordinates, placeFromLocation, placeToLocation, textPlace, type EventPlaceValue } from "./eventPlace";

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
    place: EventPlaceValue;
    onlineUrl: string;
    registrationUrl: string;
    price: string;
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
    place: textPlace(),
    onlineUrl: "",
    registrationUrl: "",
    price: "0",
    capacity: "12",
    visibility: "PUBLIC",
    joinPolicy: "OPEN",
});

type ScheduleChange = { field: "startsAt" | "endsAt"; value: string }
    | { field: "isAllDay"; value: boolean };

const isEndOfDay = (value: string) => value.slice(10) === "T23:59";

/** Keep local wall-clock values together; UTC conversion still happens on submit. */
export const updateEventSchedule = (form: EventFormState, change: ScheduleChange): EventFormState => {
    if (change.field === "endsAt") {
        return { ...form, endsAt: change.value, isAllDay: isEndOfDay(change.value) };
    }
    if (change.field === "isAllDay" && !change.value) {
        return { ...form, isAllDay: false, endsAt: isEndOfDay(form.endsAt) ? "" : form.endsAt };
    }
    const startsAt = change.field === "startsAt" ? change.value : form.startsAt;
    const isAllDay = change.field === "isAllDay" ? change.value : form.isAllDay;
    if (!isAllDay) return { ...form, startsAt };
    const startDate = startsAt.slice(0, 10);
    let endDate = form.endsAt.slice(0, 10);
    // A one-day event follows its start date. An explicitly longer range is retained.
    if (!endDate || endDate < startDate || (
        change.field === "startsAt" && endDate === form.startsAt.slice(0, 10)
    )) endDate = startDate;
    return { ...form, startsAt, isAllDay, endsAt: endDate ? `${endDate}T23:59` : "" };
};

export const formFromEvent = (event: DvizhEvent): EventFormState => ({
    title: event.title,
    description: event.description,
    tags: event.tags ?? [],
    startsAt: toDateTimeLocal(event.starts_at, event.timezone),
    endsAt: toDateTimeLocal(event.ends_at, event.timezone),
    isAllDay: event.is_all_day,
    timezone: event.timezone,
    format: event.format,
    place: placeFromLocation(event.location),
    onlineUrl: event.online_url ?? "",
    registrationUrl: event.registration_url ?? "",
    price: event.price_min ?? "",
    capacity: event.capacity?.toString() ?? "",
    visibility: event.visibility,
    joinPolicy: event.join_policy,
});

const orNull = (value: string) => value.trim() || null;

const money = (value: string) => {
    const trimmed = value.trim().replace(",", ".");
    return trimmed === "" ? null : trimmed;
};

/** Проверки, которые удобнее показать до отправки; остальное валидирует backend. */
export const validateForm = (form: EventFormState, timezone = form.timezone): string | null => {
    if (new Set(form.tags.map((tag) => tag.id)).size > MAX_EVENT_TAGS) return "Можно выбрать не больше пяти тематик.";
    try {
        new Intl.DateTimeFormat("en", { timeZone: timezone }).format();
        fromDateTimeLocal(form.startsAt, timezone);
        fromDateTimeLocal(form.endsAt, timezone);
    } catch { return "Проверьте часовой пояс и время: выбранное время может не существовать при переходе на летнее время."; }
    if (!form.title.trim()) return "Укажите название.";
    if (!form.startsAt) return "Укажите, когда начинается событие.";
    if (form.endsAt && form.endsAt <= form.startsAt) return "Окончание должно быть позже начала.";
    const location = placeToLocation(form.place);
    if (form.format !== "ONLINE" && !location?.address_line && !placeCoordinates(form.place)) {
        return "Укажите адрес или выберите место события на карте.";
    }
    if (form.format !== "ONLINE" && form.place.kind === "text" && form.place.text.trim().length > 500) return "Описание места должно быть не длиннее 500 символов.";
    if (form.format !== "ONLINE" && form.place.kind === "resolved" && (form.place.location.latitude || form.place.location.longitude) && !placeCoordinates(form.place)) return "Проверьте точку места события на карте.";
    if (form.format !== "OFFLINE" && !form.onlineUrl.trim()) return "Добавьте ссылку на трансляцию.";
    return null;
};

export const formToInput = (form: EventFormState, timezone = form.timezone): EventInput => {
    const capacity = form.capacity.trim() === "" ? null : Number(form.capacity);
    const price = money(form.price);

    return {
        title: form.title.trim(),
        description: form.description.trim(),
        tag_ids: [...new Set(form.tags.map((tag) => tag.id))],
        starts_at: fromDateTimeLocal(form.startsAt, timezone) ?? "",
        ends_at: fromDateTimeLocal(form.endsAt, timezone),
        timezone,
        is_all_day: form.isAllDay,
        format: form.format,
        location:
            form.format === "ONLINE"
                ? null
                : placeToLocation(form.place),
        online_url: form.format === "OFFLINE" ? null : orNull(form.onlineUrl),
        registration_url: orNull(form.registrationUrl),
        price_min: price,
        price_max: null,
        currency: "RUB",
        capacity: capacity !== null && Number.isFinite(capacity) ? capacity : null,
        visibility: form.visibility,
        join_policy: form.joinPolicy,
    };
};
