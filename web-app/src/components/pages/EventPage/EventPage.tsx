import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteEvent, errorText, getEvent, listParticipants } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import { MainLayout } from "../../layouts";
import { Button, Loader, Notice, Tag } from "../../ui";
import { EventCoverMain } from "../../widgets";
import {
    formatEventDate,
    formatPlace,
    formatPrice,
    FORMAT_LABELS,
    JOIN_POLICY_LABELS,
    VISIBILITY_LABELS,
} from "../../../utils/format";
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
    const [actionError, setActionError] = useState<string | null>(null);

    const eventState = useAsync(() => getEvent(id), id);
    const participantsState = useAsync(() => listParticipants(id), id);
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

    const handleDelete = async () => {
        if (!window.confirm(`Удалить событие «${event.title}»? Оно пропадёт из ленты и календарей.`)) {
            return;
        }
        try {
            await deleteEvent(event.id);
            navigate("/", { replace: true });
        } catch (err) {
            setActionError(errorText(err));
        }
    };

    return (
        <MainLayout>
            <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
                <div className="flex w-full flex-col items-start gap-[10px] rounded-lg bg-cards-surface p-8 sm:flex-row">
                    <EventCoverMain startsAt={event.starts_at} timeZone={event.timezone} />
                    <div className="flex min-w-0 flex-1 flex-col items-start gap-8 self-stretch p-[10px]">
                        <div className="flex w-full flex-col items-start gap-[10px]">
                            <h1 className="text-h1 break-words text-textprimary">{event.title}</h1>
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

                        {isOrganizer && (
                            <div className="flex flex-wrap gap-2">
                                <Button state="fixed2" className="!h-[30px] !px-4" onClick={() => navigate(`/events/${event.id}/edit`)}>
                                    Редактировать
                                </Button>
                                <Button state="hover1" className="!h-[30px] !px-4" onClick={handleDelete}>
                                    Удалить
                                </Button>
                            </div>
                        )}

                        {actionError && <Notice tone="error">{actionError}</Notice>}
                    </div>
                </div>

                <ParticipationPanel
                    event={event}
                    participants={participantsState.data}
                    participantsLoading={participantsState.loading}
                    isOrganizer={isOrganizer}
                    onChanged={reloadAll}
                />
            </section>
        </MainLayout>
    );
};
