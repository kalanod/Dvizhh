import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCalendar } from "../../../api";
import { useAsync } from "../../../hooks";
import type { DvizhEvent } from "../../../models";
import { dateBadge, formatEventDate } from "../../../utils/format";

interface CalendarRowProps {
    event: DvizhEvent;
}

/** Строка ближайшего события (MainPageFrame шаблона). */
export const CalendarRow = ({ event }: CalendarRowProps) => {
    const navigate = useNavigate();
    const badge = dateBadge(event.starts_at, event.timezone);

    return (
        <button
            type="button"
            onClick={() => navigate(`/events/${event.id}`)}
            className="flex w-full cursor-pointer items-center gap-3 rounded-xl bg-cards-surface p-2.5 text-left transition-colors hover:bg-surface-muted"
        >
            <span className="flex w-[44px] shrink-0 flex-col items-center rounded-lg bg-bordermain/10 py-1 text-bordermain">
                <span className="font-display text-[17px] leading-none font-semibold">{badge.day}</span>
                <span className="text-[10px] font-bold uppercase">{badge.month}</span>
            </span>
            <span className="flex min-w-0 flex-col">
                <span className="truncate text-body font-bold text-textprimary">{event.title}</span>
                <span className="truncate text-small font-medium text-textsecondary">{formatEventDate(event)}</span>
            </span>
        </button>
    );
};

export const CalendarPreview = ({ userId }: { userId: string }) => {
    const navigate = useNavigate();
    const { data, loading, error } = useAsync(() => getCalendar(userId), userId);
    const [now] = useState(() => Date.now());
    const upcoming = (data ?? [])
        .filter((event) => new Date(event.ends_at ?? event.starts_at).getTime() >= now)
        .slice(0, 3);

    return (
        <div className="flex flex-col gap-[8px] rounded-2xl bg-background/90 p-[14px] shadow-card">
            <div className="flex items-center justify-between px-1">
                <h2 className="text-h2 text-textthird">Мои ближайшие</h2>
                <button
                    type="button"
                    onClick={() => navigate("/calendar")}
                    className="cursor-pointer text-small text-textmuted transition hover:text-textthird"
                >
                    Весь календарь →
                </button>
            </div>
            {loading && <span className="px-1 text-small text-textmuted">Загружаем…</span>}
            {error !== undefined && <span className="px-1 text-small text-textmuted">Не удалось загрузить календарь.</span>}
            {!loading && !error && upcoming.length === 0 && (
                <span className="px-1 text-body text-textmuted">Нажмите «Иду» на событии — оно появится здесь.</span>
            )}
            {upcoming.map((event) => (
                <CalendarRow key={event.id} event={event} />
            ))}
        </div>
    );
};
