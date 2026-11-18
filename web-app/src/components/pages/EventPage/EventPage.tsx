import { useEffect, useRef, type ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { errorText, getEvent, listParticipants } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import { MainLayout } from "../../layouts";
import { EventTitle, Loader, Notice, Tag } from "../../ui";
import { EventCoverMain, PersonalToggles } from "../../widgets";
import {
    EVENT_STATUS_LABELS,
    formatEventDate,
    formatPlace,
    formatPrice,
    FORMAT_LABELS,
    JOIN_POLICY_LABELS,
    VISIBILITY_LABELS,
} from "../../../utils/format";
import type { EventNavigationState } from "../../../utils/eventDetails";
import { recordInteraction } from "../../../utils/interactions";
import { InvitePanel } from "./InvitePanel";
import { OrganizerPanel } from "./OrganizerPanel";
import { ParticipationPanel } from "./ParticipationPanel";
import { EventLocationMap } from "../../widgets/EventLocation/EventLocationMap";

const Row = ({ label, children }: { label: string; children: ReactNode }) => (
    <div className="flex flex-wrap items-center gap-2">
        <span className="text-h3 text-textsecondary">{label}:</span>
        {children}
    </div>
);

export const EventPage = () => {
    const { id = "" } = useParams();
    const navigate = useNavigate();
    const { userId } = useCurrentUser();
    const location = useLocation();
    const state = location.state as EventNavigationState | null;
    const occurrenceId = new URLSearchParams(location.search).get("occurrence_id");
    const interactionOrigin = userId && state?.attribution?.userId === userId ? state.attribution.origin : undefined;

    const eventState = useAsync((signal) => getEvent(id, userId, signal, occurrenceId), `${id}:${occurrenceId}:${userId}`);
    const participantsState = useAsync((signal) => listParticipants(id, signal, occurrenceId), `${id}:${occurrenceId}`);
    const event = eventState.data;
    const lastOpen = useRef<string | null>(null);
    const itemId = event?.id;
    useEffect(() => {
        if (!userId || !itemId) return;
        const key = `${location.key}:${userId}:${itemId}`;
        if (lastOpen.current === key) return;
        if (recordInteraction(userId, itemId, "OPEN", interactionOrigin)) lastOpen.current = key;
    }, [location.key, userId, itemId, interactionOrigin]);

    const reloadAll = () => {
        eventState.reload();
        participantsState.reload();
    };

    if (!event) {
        return (
            <MainLayout>
                <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
                    <div className="flex w-full items-center justify-center p-8">
                        {eventState.loading ? <Loader /> : <p className="text-h2 text-textprimary">{errorText(eventState.error)}</p>}
                    </div>
                </section>
            </MainLayout>
        );
    }

    const isOrganizer = Boolean(userId && event.organizer?.id === userId);
    const isFree = event.price_type === "FREE" || !event.price_min;
    const canInvite = isOrganizer && event.status === "PUBLISHED" && event.join_policy !== "EXTERNAL";
    const recordExternalClick = () => recordInteraction(userId, event.id, "EXTERNAL_LINK_CLICK", interactionOrigin);

    return (
        <MainLayout>
            <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
                <div className="flex w-full flex-col items-start gap-[10px] rounded-lg bg-cards-surface p-4 sm:flex-row sm:p-8">
                    <EventCoverMain startsAt={event.starts_at} timeZone={event.timezone} coverUrl={event.cover_url} viewerId={userId} />
                    <div className="flex min-w-0 flex-1 flex-col items-start gap-6 self-stretch p-0 sm:gap-8 sm:p-[10px]">
                        <div className="flex w-full flex-col items-start gap-[10px]">
                            {event.status !== "PUBLISHED" && (
                                <Tag
                                    label={EVENT_STATUS_LABELS[event.status]}
                                    variant={event.status === "CANCELLED" ? "price" : "muted"}
                                />
                            )}
                            <h1 className={`text-h1 break-words text-textprimary ${event.status === "CANCELLED" ? "line-through opacity-70" : ""}`}>
                                <EventTitle title={event.title} />
                            </h1>
                            <PersonalToggles event={event} onChange={eventState.reload} />
                            {event.organizer && (
                                <Row label="Организатор">
                                    <button
                                        type="button"
                                        onClick={() => navigate(`/users/${event.organizer?.id}`)}
                                        className="cursor-pointer text-body text-textghost hover:opacity-80"
                                    >
                                        {event.organizer.display_name}
                                    </button>
                                </Row>
                            )}
                        </div>

                        <div className="flex w-full flex-col items-start gap-[10px]">
                            <Row label="Когда">
                                <span className="text-body text-textprimary">{formatEventDate(event)}</span>
                            </Row>
                            <Row label="Где">
                                <span className="text-body text-textprimary">{formatPlace(event)}</span>
                            </Row>
                            <Row label="Стоимость">
                                <Tag label={formatPrice(event)} variant={isFree ? "free" : "price"} />
                            </Row>
                            <Row label="Формат">
                                <Tag label={FORMAT_LABELS[event.format]} variant="format" />
                            </Row>
                            <Row label="Вход">
                                <Tag label={JOIN_POLICY_LABELS[event.join_policy]} variant="policy" />
                            </Row>
                            <Row label="Видимость">
                                <span className="text-body text-textprimary">{VISIBILITY_LABELS[event.visibility]}</span>
                            </Row>
                            {event.tags.length > 0 && (
                                <Row label="Тематики">
                                    <div className="flex flex-wrap gap-2">
                                        {event.tags.map((tag) => (
                                            <Tag key={tag.id} label={tag.name} color={tag.category.color} onClick={() => navigate(`/?tag_id=${encodeURIComponent(tag.id)}`)} />
                                        ))}
                                    </div>
                                </Row>
                            )}
                            {event.online_url && (
                                <Row label="Трансляция">
                                    <a href={event.online_url} target="_blank" rel="noreferrer" onClick={recordExternalClick} className="text-body break-all text-textghost hover:opacity-80">
                                        {event.online_url}
                                    </a>
                                </Row>
                            )}
                            {event.registration_url && (
                                <Row label="Регистрация">
                                    <a
                                        href={event.registration_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        onClick={recordExternalClick}
                                        className="text-body break-all text-textghost hover:opacity-80"
                                    >
                                        {event.registration_url}
                                    </a>
                                </Row>
                            )}
                        </div>

                        <div className="flex w-full flex-col gap-2">
                            <span className="text-h3 text-textsecondary">Описание:</span>
                            <p className="text-body whitespace-pre-line text-textprimary">
                                {event.description || "Организатор пока не добавил описание."}
                            </p>
                        </div>

                        {event.status === "CANCELLED" && <Notice tone="error">Событие отменено организатором.</Notice>}
                        {state?.notice && <Notice tone="error">{state.notice}</Notice>}

                        {isOrganizer && userId && <OrganizerPanel event={event} userId={userId} onChanged={reloadAll} />}
                    </div>
                </div>

                {event.format !== "ONLINE" && event.location && (
                    <div className="flex w-full flex-col gap-3 rounded-lg bg-cards-surface p-4 sm:p-8">
                        <h2 className="text-h2 text-textprimary">Место проведения</h2>
                        <p className="text-body text-textprimary">{formatPlace(event)}</p>
                        <EventLocationMap location={event.location} />
                    </div>
                )}

                <ParticipationPanel
                    key={`${event.occurrence_id}:${userId}`}
                    event={event}
                    interactionOrigin={interactionOrigin}
                    participants={participantsState.data}
                    participantsLoading={participantsState.loading}
                    isOrganizer={isOrganizer}
                    onChanged={reloadAll}
                />

                {canInvite && userId && <InvitePanel event={event} userId={userId} participants={participantsState.data} />}
            </section>
        </MainLayout>
    );
};
