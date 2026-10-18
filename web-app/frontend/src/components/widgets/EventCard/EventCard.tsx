import { useNavigate } from "react-router-dom";
import { Avatar, Tag } from "../../ui";
import type { DvizhEvent } from "../../../models";
import {
    dateBadge,
    formatEventDate,
    formatGoing,
    formatPlace,
    formatPrice,
    formatSeats,
    FORMAT_LABELS,
    JOIN_POLICY_LABELS,
    seatsLeft,
} from "../../../utils/format";

interface EventCardProps {
    event: DvizhEvent;
    onTagClick?: (tag: string) => void;
    className?: string;
}

/** Карточка события: по ней можно принять решение, не открывая подробную страницу. */
export const EventCard = ({ event, onTagClick, className = "" }: EventCardProps) => {
    const navigate = useNavigate();
    const badge = dateBadge(event.starts_at, event.timezone);
    const seats = seatsLeft(event);
    const isFree = event.price_type === "FREE" || !event.price_min;

    return (
        <article
            onClick={() => navigate(`/events/${event.id}`)}
            className={`group flex w-full cursor-pointer gap-4 rounded-2xl bg-cards-surface p-4 shadow-card transition-all hover:-translate-y-0.5 hover:shadow-hover ${className}`}
        >
            <div className="flex h-[76px] w-[64px] shrink-0 flex-col items-center justify-center rounded-xl bg-gradient-to-br from-borderlight to-bordermain text-textthird">
                <span className="font-display text-[26px] leading-none font-semibold">{badge.day}</span>
                <span className="mt-1 text-small uppercase">{badge.month}</span>
            </div>

            <div className="flex min-w-0 flex-1 flex-col gap-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                    <h3 className="min-w-0 text-h3 text-textprimary transition-colors group-hover:text-bordermain">
                        <a
                            href={`/events/${event.id}`}
                            onClick={(e) => {
                                e.preventDefault();
                            }}
                        >
                            {event.title}
                        </a>
                    </h3>
                    <Tag label={formatPrice(event)} variant={isFree ? "free" : "price"} />
                </div>

                <div className="flex flex-col gap-0.5 text-body text-textsecondary">
                    <span>🗓 {formatEventDate(event)}</span>
                    <span className="truncate">📍 {formatPlace(event)}</span>
                </div>

                {event.description && <p className="line-clamp-2 text-body text-textprimary/80">{event.description}</p>}

                <div className="flex flex-wrap gap-1.5">
                    {event.tags.map((tag) => (
                        <Tag key={tag} label={tag} variant="topic" onClick={onTagClick ? () => onTagClick(tag) : undefined} />
                    ))}
                    {event.format !== "OFFLINE" && <Tag label={FORMAT_LABELS[event.format]} variant="format" />}
                    {event.join_policy !== "OPEN" && <Tag label={JOIN_POLICY_LABELS[event.join_policy]} variant="policy" />}
                </div>

                <div className="mt-1 flex flex-wrap items-center justify-between gap-2 border-t border-bordersoft pt-2 text-small text-textsecondary">
                    {event.organizer ? (
                        <span className="flex min-w-0 items-center gap-2">
                            <Avatar name={event.organizer.display_name} seed={event.organizer.id} size="sm" />
                            <span className="truncate">{event.organizer.display_name}</span>
                        </span>
                    ) : (
                        <span />
                    )}
                    <span>
                        {formatGoing(event.participants_count)}
                        {seats !== null && (
                            <span className={seats === 0 ? "text-texterror" : "text-textsuccess"}>
                                {" · "}
                                {seats === 0 ? "мест нет" : `осталось ${formatSeats(seats)}`}
                            </span>
                        )}
                    </span>
                </div>
            </div>
        </article>
    );
};
