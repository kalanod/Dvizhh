import type { ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { errorText, getEvent, listParticipants, mediaSrc } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import { MainLayout } from "../../layouts";
import { Loader, Notice, Tag } from "../../ui";
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
import { InvitePanel } from "./InvitePanel";
import { OrganizerPanel } from "./OrganizerPanel";
import { ParticipationPanel } from "./ParticipationPanel";

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
    // Предупреждение от формы: событие сохранено, а обложка — нет.
    const formNotice = (useLocation().state as { notice?: string } | null)?.notice;

    const eventState = useAsync((signal) => getEvent(id, userId, signal), `${id}:${userId}`);
    const participantsState = useAsync((signal) => listParticipants(id, signal), id);
    const event = eventState.data;

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

    return (
        <MainLayout>
            <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
                <div className="flex w-full flex-col items-start gap-[10px] rounded-lg bg-cards-surface p-4 sm:flex-row sm:p-8">
                    <EventCoverMain startsAt={event.starts_at} timeZone={event.timezone} src={mediaSrc(event.cover_url, userId)} />
                    <div className="flex min-w-0 flex-1 flex-col items-start gap-6 self-stretch p-0 sm:gap-8 sm:p-[10px]">
                        <div className="flex w-full flex-col items-start gap-[10px]">
                            {event.status !== "PUBLISHED" && (
                                <Tag
                                    label={EVENT_STATUS_LABELS[event.status]}
                                    variant={event.status === "CANCELLED" ? "price" : "muted"}
                                />
                            )}
                            <h1 className={`text-h1 break-words text-textprimary ${event.status === "CANCELLED" ? "line-through opacity-70" : ""}`}>
                                {event.title}
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
                                            <Tag key={tag} label={tag} onClick={() => navigate(`/?tag=${encodeURIComponent(tag)}`)} />
                                        ))}
                                    </div>
                                </Row>
                            )}
                            {event.online_url && (
                                <Row label="Трансляция">
                                    <a href={event.online_url} target="_blank" rel="noreferrer" className="text-body break-all text-textghost hover:opacity-80">
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
                        {formNotice && <Notice tone="error">{formNotice}</Notice>}

                        {isOrganizer && userId && <OrganizerPanel event={event} userId={userId} onChanged={reloadAll} />}
                    </div>
                </div>

                <ParticipationPanel
                    event={event}
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
