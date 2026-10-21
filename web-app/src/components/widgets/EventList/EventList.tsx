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

/** Список событий в виде BookList шаблона. */
export const EventList = ({
    title,
    actionButton,
    events,
    loading = false,
    error,
    emptyText = "Событий пока нет",
    footer,
    onTagClick,
    className = "",
}: EventListProps) => (
    <div className={`flex w-full flex-col items-start gap-[10px] rounded-lg bg-background p-[10px] ${className}`}>
        {title && <h1 className="text-h1 text-textthird">{title}</h1>}

        {actionButton && <div className="flex w-full flex-wrap gap-2">{actionButton}</div>}

        {error && <Notice tone="error">{error}</Notice>}

        {events?.map((event) => <EventCard key={event.id} event={event} onTagClick={onTagClick} />)}

        {loading && <Loader />}

        {!loading && !error && events?.length === 0 && (
            <div className="flex w-full items-center justify-center p-8">
                <p className="text-h3 text-textthird">{emptyText}</p>
            </div>
        )}

        {footer}
    </div>
);
