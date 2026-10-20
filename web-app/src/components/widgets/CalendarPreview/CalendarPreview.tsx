import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCalendar } from "../../../api";
import { useAsync } from "../../../hooks";
import type { DvizhEvent } from "../../../models";
import { formatEventDate } from "../../../utils/format";
import { ButtonGhost } from "../../ui";

/** Строка ближайшего события (MainPageFrame шаблона). */
export const CalendarRow = ({ event }: { event: DvizhEvent }) => {
    const navigate = useNavigate();

    return (
        <div
            onClick={() => navigate(`/events/${event.id}`)}
            className="flex min-h-[42px] w-full cursor-pointer flex-col justify-center gap-0.5 overflow-hidden rounded-lg bg-cards-surface p-2.5 transition-colors hover:bg-cards-surface/80"
        >
            <div className="text-duration text-textsecondary">{formatEventDate(event)}</div>
            <div className="truncate text-body text-black">{event.title}</div>
        </div>
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
        <div className="flex flex-col gap-[10px] rounded-lg bg-background p-[10px]">
            <div className="flex items-center justify-between px-2">
                <h3 className="text-h3 text-textprimary">Ближайшие</h3>
                <ButtonGhost text="Весь календарь" className="!text-textthird" onClick={() => navigate("/calendar")} />
            </div>
            {loading && <span className="px-2 text-small text-textthird">Загрузка...</span>}
            {error !== undefined && <span className="px-2 text-small text-textthird">Не удалось загрузить календарь</span>}
            {!loading && !error && upcoming.length === 0 && (
                <div className="rounded-lg bg-cards-surface p-2.5 text-body text-textsecondary">
                    Нажмите «Иду» на событии — оно появится здесь
                </div>
            )}
            {upcoming.map((event) => (
                <CalendarRow key={event.id} event={event} />
            ))}
        </div>
    );
};
