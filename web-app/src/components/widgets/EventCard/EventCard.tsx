import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { mediaSrc } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import { Tag } from "../../ui";
import type { DvizhEvent } from "../../../models";
import {
    EVENT_STATUS_LABELS,
    formatEventDate,
    formatGoing,
    formatPlace,
    formatPrice,
    formatSeats,
    FORMAT_LABELS,
    JOIN_POLICY_LABELS,
    seatsLeft,
} from "../../../utils/format";
import { EventCoverMicro } from "./EventCoverMicro";
import { PersonalToggles } from "./PersonalToggles";

interface EventCardProps {
    event: DvizhEvent;
    onTagClick?: (tag: string) => void;
    /** Вызывается после «В избранное» / «Не интересно» с обновлённой карточкой. */
    onPersonalChange?: (event: DvizhEvent) => void;
    /** В ленте скрытое событие сворачивается в строку с кнопкой «Вернуть». */
    collapseDismissed?: boolean;
    className?: string;
}

/** Карточка события в виде BookCard шаблона. */
export const EventCard = ({ event: initial, onTagClick, onPersonalChange, collapseDismissed = false, className = "" }: EventCardProps) => {
    const navigate = useNavigate();
    const { userId } = useCurrentUser();
    // Ответ backend-а на переключатели действует, пока родитель не передал новую карточку.
    const [updated, setUpdated] = useState<{ from: DvizhEvent; to: DvizhEvent } | null>(null);
    const event = updated?.from === initial ? updated.to : initial;
    const seats = seatsLeft(event);
    const isFree = event.price_type === "FREE" || !event.price_min;

    const handlePersonalChange = (next: DvizhEvent) => {
        setUpdated({ from: initial, to: next });
        onPersonalChange?.(next);
    };

    if (collapseDismissed && event.personal_state?.is_dismissed) {
        return (
            <div className={`flex w-full flex-wrap items-center justify-between gap-2 rounded-lg bg-cards-surface/70 px-4 py-3 ${className}`}>
                <span className="min-w-0 truncate text-body text-textsecondary">
                    «{event.title}» скрыто из вашей ленты
                </span>
                <PersonalToggles event={event} onChange={handlePersonalChange} />
            </div>
        );
    }

    return (
        <article
            className={`flex w-full cursor-pointer gap-[10px] rounded-lg bg-cards-surface p-3 sm:p-4 transition-all hover:scale-[1.01] hover:shadow-lg ${className}`}
            onClick={() => navigate(`/events/${event.id}`)}
        >
            <div className="h-[128px] w-[86px] flex-shrink-0 max-sm:hidden">
                <EventCoverMicro startsAt={event.starts_at} timeZone={event.timezone} src={mediaSrc(event.cover_url, userId)} />
            </div>

            <div className="flex min-w-0 flex-1 flex-col justify-between gap-4">
                {/* На телефоне обложка-дата не помещается сбоку — дата и так есть в тексте карточки. */}
                <div className="flex w-full flex-wrap gap-4">
                    <div className="flex min-w-[min(200px,100%)] flex-1 flex-col gap-2 py-1">
                        <h3 className="text-h3 break-words text-textprimary transition-colors hover:text-primary">{event.title}</h3>
                        <span className="text-duration text-textsecondary">{formatEventDate(event)}</span>
                        <span className="text-body text-textprimary">{formatPlace(event)}</span>
                        {event.organizer && (
                            <span className="text-body text-textsecondary">Организатор: {event.organizer.display_name}</span>
                        )}
                    </div>

                    <div className="flex w-full flex-col gap-2 py-1 sm:w-[160px]">
                        {event.status !== "PUBLISHED" && <Tag label={EVENT_STATUS_LABELS[event.status]} variant="muted" />}
                        <Tag label={formatPrice(event)} variant={isFree ? "free" : "price"} />
                        {event.format !== "OFFLINE" && <Tag label={FORMAT_LABELS[event.format]} variant="format" />}
                        {event.join_policy !== "OPEN" && <Tag label={JOIN_POLICY_LABELS[event.join_policy]} variant="policy" />}
                        <span className="text-small text-textsecondary">
                            {formatGoing(event.participants_count)}
                            {seats !== null && (seats === 0 ? " · мест нет" : ` · осталось ${formatSeats(seats)}`)}
                        </span>
                    </div>
                </div>

                {(event.tags.length > 0 || userId) && (
                    <div className="flex w-full flex-wrap items-center justify-between gap-2 py-1">
                        <div className="flex flex-wrap gap-1">
                            {event.tags.map((tag) => (
                                <Tag key={tag} label={tag} variant="topic" onClick={onTagClick ? () => onTagClick(tag) : undefined} />
                            ))}
                        </div>
                        <PersonalToggles event={event} onChange={handlePersonalChange} />
                    </div>
                )}
            </div>
        </article>
    );
};
