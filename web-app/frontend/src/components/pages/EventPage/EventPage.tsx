import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { deleteEvent, errorText, getEvent, listParticipants } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import { MainLayout } from "../../layouts";
import { Avatar, Button, Loader, Notice, Tag } from "../../ui";
import {
    formatEventDate,
    formatPlace,
    formatPrice,
    FORMAT_LABELS,
    JOIN_POLICY_LABELS,
    VISIBILITY_LABELS,
} from "../../../utils/format";
import { ParticipationPanel } from "./ParticipationPanel";

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

    if (eventState.loading && !event) {
        return (
            <MainLayout>
                <Loader />
            </MainLayout>
        );
    }

    if (!event) {
        return (
            <MainLayout>
                <Notice tone="error">{errorText(eventState.error)}</Notice>
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

    const details = [
        { icon: "🗓", label: "Когда", value: formatEventDate(event) },
        { icon: "📍", label: "Где", value: formatPlace(event) },
        { icon: "💳", label: "Стоимость", value: formatPrice(event) },
        { icon: "🚪", label: "Вход", value: JOIN_POLICY_LABELS[event.join_policy] },
        { icon: "👀", label: "Видимость", value: VISIBILITY_LABELS[event.visibility] },
    ];

    return (
        <MainLayout>
            <div className="flex w-full flex-col gap-[12px] lg:flex-row lg:items-start">
                <article className="flex min-w-0 flex-1 flex-col gap-5 rounded-2xl bg-cards-surface p-6 shadow-card sm:p-8">
                    <button
                        type="button"
                        onClick={() => navigate(-1)}
                        className="w-fit cursor-pointer text-small text-textsecondary transition hover:text-bordermain"
                    >
                        ← Назад
                    </button>

                    <div className="flex flex-col gap-3">
                        <div className="flex flex-wrap gap-1.5">
                            <Tag label={formatPrice(event)} variant={isFree ? "free" : "price"} />
                            <Tag label={FORMAT_LABELS[event.format]} variant="format" />
                            {event.status !== "PUBLISHED" && <Tag label={event.status} variant="muted" />}
                        </div>
                        <h1 className="text-h1 break-words text-textprimary">{event.title}</h1>
                        {event.tags.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                                {event.tags.map((tag) => (
                                    <Tag key={tag} label={tag} onClick={() => navigate(`/?tag=${encodeURIComponent(tag)}`)} />
                                ))}
                            </div>
                        )}
                    </div>

                    <dl className="grid gap-3 sm:grid-cols-2">
                        {details.map((item) => (
                            <div key={item.label} className="flex gap-3 rounded-xl bg-surface-muted p-3">
                                <span aria-hidden="true" className="text-[20px]">
                                    {item.icon}
                                </span>
                                <div className="flex min-w-0 flex-col">
                                    <dt className="text-small text-textsecondary">{item.label}</dt>
                                    <dd className="text-body font-bold break-words text-textprimary">{item.value}</dd>
                                </div>
                            </div>
                        ))}
                    </dl>

                    {(event.online_url || event.registration_url) && (
                        <div className="flex flex-wrap gap-2">
                            {event.online_url && (
                                <a
                                    href={event.online_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex h-[41px] items-center rounded-xl border-2 border-bordermain px-5 text-buttons text-bordermain transition hover:bg-bordermain hover:text-textthird"
                                >
                                    Ссылка на трансляцию ↗
                                </a>
                            )}
                            {event.registration_url && (
                                <a
                                    href={event.registration_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex h-[41px] items-center rounded-xl border-2 border-bordermain px-5 text-buttons text-bordermain transition hover:bg-bordermain hover:text-textthird"
                                >
                                    Регистрация / билеты ↗
                                </a>
                            )}
                        </div>
                    )}

                    <section className="flex flex-col gap-2">
                        <h2 className="text-h2 text-textprimary">Описание</h2>
                        <p className="text-body whitespace-pre-line text-textprimary/85">
                            {event.description || "Организатор пока не добавил описание."}
                        </p>
                    </section>

                    {event.organizer && (
                        <button
                            type="button"
                            onClick={() => navigate(`/users/${event.organizer?.id}`)}
                            className="flex w-fit cursor-pointer items-center gap-3 rounded-xl border border-bordersoft p-3 pr-5 text-left transition hover:border-bordermain"
                        >
                            <Avatar name={event.organizer.display_name} seed={event.organizer.id} />
                            <span className="flex flex-col">
                                <span className="text-small text-textsecondary">Организатор</span>
                                <span className="text-body font-bold text-textprimary">{event.organizer.display_name}</span>
                            </span>
                        </button>
                    )}

                    {isOrganizer && (
                        <div className="flex flex-wrap gap-2 border-t border-bordersoft pt-4">
                            <Button state="hover2" onClick={() => navigate(`/events/${event.id}/edit`)}>
                                Редактировать
                            </Button>
                            <button
                                type="button"
                                onClick={handleDelete}
                                className="inline-flex h-[41px] cursor-pointer items-center rounded-xl border-2 border-bordererror px-5 text-buttons text-texterror transition hover:bg-error hover:text-textthird"
                            >
                                Удалить
                            </button>
                        </div>
                    )}

                    {actionError && <Notice tone="error">{actionError}</Notice>}
                </article>

                <ParticipationPanel
                    event={event}
                    participants={participantsState.data}
                    participantsLoading={participantsState.loading}
                    isOrganizer={isOrganizer}
                    onChanged={reloadAll}
                />
            </div>
        </MainLayout>
    );
};
