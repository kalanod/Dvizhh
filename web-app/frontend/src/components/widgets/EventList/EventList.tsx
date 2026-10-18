import type { ReactNode } from "react";
import { EventCard } from "../EventCard";
import { Loader, Notice } from "../../ui";
import type { DvizhEvent } from "../../../models";

interface EventListProps {
    title?: string;
    actionButton?: ReactNode;
    events: DvizhEvent[] | undefined;
    loading?: boolean;
    error?: string | null;
    emptyText?: ReactNode;
    footer?: ReactNode;
    onTagClick?: (tag: string) => void;
    className?: string;
}

export const EventList = ({
    title,
    actionButton,
    events,
    loading = false,
    error,
    emptyText = "Событий пока нет.",
    footer,
    onTagClick,
    className = "",
}: EventListProps) => (
    <div className={`flex w-full flex-col items-start gap-[12px] rounded-2xl bg-background/90 p-[14px] shadow-card ${className}`}>
        {title && <h1 className="text-h1 text-textthird">{title}</h1>}

        {actionButton && <div className="flex w-full flex-wrap gap-2">{actionButton}</div>}

        {error && <Notice tone="error" className="w-full">{error}</Notice>}

        {events?.map((event) => <EventCard key={event.id} event={event} onTagClick={onTagClick} />)}

        {loading && <Loader />}

        {!loading && !error && events?.length === 0 && (
            <div className="w-full rounded-2xl border-2 border-dashed border-textmuted/25 px-6 py-10 text-center text-body text-textmuted">
                {emptyText}
            </div>
        )}

        {footer}
    </div>
);
