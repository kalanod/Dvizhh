import type { DvizhEvent, EventFormat, EventJoinPolicy, EventVisibility, ParticipationStatus } from "../models";

export const FORMAT_LABELS: Record<EventFormat, string> = {
    OFFLINE: "Офлайн",
    ONLINE: "Онлайн",
    HYBRID: "Офлайн + онлайн",
};

export const JOIN_POLICY_LABELS: Record<EventJoinPolicy, string> = {
    OPEN: "Свободный вход",
    REQUEST: "По заявке",
    INVITE_ONLY: "По приглашению",
    EXTERNAL: "Регистрация на сайте",
};

export const VISIBILITY_LABELS: Record<EventVisibility, string> = {
    PUBLIC: "Всем — в общей ленте",
    FRIENDS: "Только друзьям",
    UNLISTED: "По прямой ссылке",
    PRIVATE: "Только приглашённым",
};

export const PARTICIPATION_LABELS: Record<ParticipationStatus, string> = {
    GOING: "Идёт",
    REQUESTED: "Заявка",
    REJECTED: "Отклонено",
    CANCELLED: "Отменено",
};

const sameDay = (a: Date, b: Date, timeZone: string) =>
    a.toLocaleDateString("ru-RU", { timeZone }) === b.toLocaleDateString("ru-RU", { timeZone });

/** «сб, 25 окт · 19:00–22:00» в часовом поясе события. */
export const formatEventDate = (event: Pick<DvizhEvent, "starts_at" | "ends_at" | "is_all_day" | "timezone">) => {
    const timeZone = event.timezone || undefined;
    const start = new Date(event.starts_at);
    const end = event.ends_at ? new Date(event.ends_at) : null;
    const day = (date: Date) =>
        date.toLocaleDateString("ru-RU", { timeZone, weekday: "short", day: "numeric", month: "short" });
    const time = (date: Date) => date.toLocaleTimeString("ru-RU", { timeZone, hour: "2-digit", minute: "2-digit" });

    if (event.is_all_day) {
        return end && !sameDay(start, end, event.timezone) ? `${day(start)} – ${day(end)}` : `${day(start)} · весь день`;
    }
    if (!end) {
        return `${day(start)} · ${time(start)}`;
    }
    if (sameDay(start, end, event.timezone)) {
        return `${day(start)} · ${time(start)}–${time(end)}`;
    }
    return `${day(start)} ${time(start)} – ${day(end)} ${time(end)}`;
};

/** Короткая плашка даты для карточки: число и месяц. */
export const dateBadge = (iso: string, timeZone?: string) => {
    const date = new Date(iso);
    return {
        day: date.toLocaleDateString("ru-RU", { timeZone, day: "numeric" }),
        month: date.toLocaleDateString("ru-RU", { timeZone, month: "short" }).replace(".", ""),
    };
};

export const formatMonth = (iso: string) => {
    const label = new Date(iso).toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
    return label.charAt(0).toUpperCase() + label.slice(1);
};

export const formatJoinedAt = (iso: string) =>
    new Date(iso).toLocaleDateString("ru-RU", { month: "long", year: "numeric" });

const money = (value: string, currency: string) =>
    new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(value));

export const formatPrice = (event: Pick<DvizhEvent, "price_type" | "price_min" | "price_max" | "currency">) => {
    if (event.price_type === "FREE" || !event.price_min) {
        return "Бесплатно";
    }
    const currency = event.currency ?? "RUB";
    if (event.price_max && event.price_max !== event.price_min) {
        return `${money(event.price_min, currency)} – ${money(event.price_max, currency)}`;
    }
    return money(event.price_min, currency);
};

export const formatPlace = (event: Pick<DvizhEvent, "format" | "location">) => {
    const parts = [event.location?.name, event.location?.address_line, event.location?.city].filter(Boolean);
    if (event.format === "ONLINE") {
        return "Онлайн";
    }
    const place = parts.length > 0 ? parts.join(", ") : "Место уточняется";
    return event.format === "HYBRID" ? `${place} + онлайн` : place;
};

export const seatsLeft = (event: Pick<DvizhEvent, "capacity" | "participants_count">) =>
    event.capacity === null ? null : Math.max(event.capacity - event.participants_count, 0);

const plural = (n: number, one: string, few: string, many: string) => {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return one;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
    return many;
};

export const formatGoing = (count: number) => (count === 0 ? "Пока никто не идёт" : `${count} ${plural(count, "идёт", "идут", "идут")}`);

export const formatSeats = (count: number) => `${count} ${plural(count, "место", "места", "мест")}`;

/** ISO-время → значение для <input type="datetime-local"> в часовом поясе браузера. */
export const toDateTimeLocal = (iso: string | null) => {
    if (!iso) return "";
    const date = new Date(iso);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
};

/** Значение <input type="datetime-local"> → ISO с часовым поясом. */
export const fromDateTimeLocal = (value: string) => (value ? new Date(value).toISOString() : null);

export const browserTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow";
