import { useNavigate } from "react-router-dom";
import { Tag } from "../../ui";
import type { DvizhEvent } from "../../../models";
import {
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

interface EventCardProps {
    event: DvizhEvent;
    onTagClick?: (tag: string) => void;
    className?: string;
}

/** Карточка события в виде BookCard шаблона. */
export const EventCard = ({ event, onTagClick, className = "" }: EventCardProps) => {
    const navigate = useNavigate();
    const seats = seatsLeft(event);
    const isFree = event.price_type === "FREE" || !event.price_min;

    return (
        <article
            className={`flex w-full cursor-pointer gap-[10px] rounded-lg bg-cards-surface p-4 transition-all hover:scale-[1.01] hover:shadow-lg ${className}`}
            onClick={() => navigate(`/events/${event.id}`)}
        >
            <div className="h-[128px] w-[86px] flex-shrink-0">
                <EventCoverMicro startsAt={event.starts_at} timeZone={event.timezone} />
            </div>

            <div className="flex min-w-0 flex-1 flex-col justify-between gap-4">
                <div className="flex w-full flex-wrap gap-4">
                    <div className="flex min-w-[200px] flex-1 flex-col gap-2 py-1">
                        <h3 className="text-h3 text-textprimary transition-colors hover:text-primary">{event.title}</h3>
                        <span className="text-duration text-textsecondary">{formatEventDate(event)}</span>
                        <span className="text-body text-textprimary">{formatPlace(event)}</span>
                        {event.organizer && (
                            <span className="text-body text-textsecondary">Организатор: {event.organizer.display_name}</span>
                        )}
                    </div>

                    <div className="flex w-[160px] flex-col gap-2 py-1">
                        <Tag label={formatPrice(event)} variant={isFree ? "free" : "price"} />
                        {event.format !== "OFFLINE" && <Tag label={FORMAT_LABELS[event.format]} variant="format" />}
                        {event.join_policy !== "OPEN" && <Tag label={JOIN_POLICY_LABELS[event.join_policy]} variant="policy" />}
                        <span className="text-small text-textsecondary">
                            {formatGoing(event.participants_count)}
                            {seats !== null && (seats === 0 ? " · мест нет" : ` · осталось ${formatSeats(seats)}`)}
                        </span>
                    </div>
                </div>

                {event.tags.length > 0 && (
                    <div className="flex w-full flex-wrap gap-1 py-1">
                        {event.tags.map((tag) => (
                            <Tag key={tag} label={tag} variant="topic" onClick={onTagClick ? () => onTagClick(tag) : undefined} />
                        ))}
                    </div>
                )}
            </div>
        </article>
    );
};
