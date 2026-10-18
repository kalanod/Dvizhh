import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText, joinEvent, leaveEvent, reviewParticipation } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import type { DvizhEvent, Participant } from "../../../models";
import { Button, Notice } from "../../ui";
import { PeopleList } from "../../widgets";
import { formatGoing, formatSeats, PARTICIPATION_LABELS, seatsLeft } from "../../../utils/format";

interface ParticipationPanelProps {
    event: DvizhEvent;
    participants: Participant[] | undefined;
    participantsLoading: boolean;
    isOrganizer: boolean;
    onChanged: () => void;
}

/** Блок «Иду»: участие текущего пользователя, список участников и рассмотрение заявок. */
export const ParticipationPanel = ({
    event,
    participants,
    participantsLoading,
    isOrganizer,
    onChanged,
}: ParticipationPanelProps) => {
    const navigate = useNavigate();
    const { userId } = useCurrentUser();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const seats = seatsLeft(event);
    const myStatus = participants?.find((p) => p.user.id === userId)?.status;
    const going = participants?.filter((p) => p.status === "GOING") ?? [];
    const requests = participants?.filter((p) => p.status === "REQUESTED") ?? [];

    const run = async (action: () => Promise<unknown>, success: string) => {
        setBusy(true);
        setError(null);
        setMessage(null);
        try {
            await action();
            setMessage(success);
            onChanged();
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    };

    const renderAction = () => {
        if (!userId) {
            return (
                <Button state="hover1" className="w-full" onClick={() => navigate(`/login?next=/events/${event.id}`)}>
                    Войти, чтобы пойти
                </Button>
            );
        }
        if (myStatus === "GOING") {
            return (
                <>
                    <Notice tone="success">Вы идёте! Событие уже в вашем календаре.</Notice>
                    <Button
                        state="outline"
                        className="w-full"
                        disabled={busy}
                        onClick={() => run(() => leaveEvent(event.id, userId), "Участие отменено.")}
                    >
                        Отменить участие
                    </Button>
                </>
            );
        }
        if (myStatus === "REQUESTED") {
            return (
                <>
                    <Notice>Заявка отправлена — ждём решения организатора.</Notice>
                    <Button
                        state="outline"
                        className="w-full"
                        disabled={busy}
                        onClick={() => run(() => leaveEvent(event.id, userId), "Заявка отозвана.")}
                    >
                        Отозвать заявку
                    </Button>
                </>
            );
        }
        switch (event.join_policy) {
            case "OPEN":
                return (
                    <Button
                        state="hover1"
                        className="w-full"
                        disabled={busy || seats === 0}
                        onClick={() => run(() => joinEvent(event.id, userId), "Готово, вы в списке участников!")}
                    >
                        {seats === 0 ? "Мест нет" : "Иду"}
                    </Button>
                );
            case "REQUEST":
                return (
                    <Button
                        state="hover1"
                        className="w-full"
                        disabled={busy || seats === 0}
                        onClick={() => run(() => joinEvent(event.id, userId), "Заявка отправлена организатору.")}
                    >
                        {seats === 0 ? "Мест нет" : "Подать заявку"}
                    </Button>
                );
            case "INVITE_ONLY":
                return <Notice>Попасть можно только по приглашению организатора.</Notice>;
            case "EXTERNAL":
                return event.registration_url ? (
                    <a
                        href={event.registration_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-[41px] w-full items-center justify-center rounded-xl bg-borderlight text-buttons text-textthird transition hover:shadow-hover"
                    >
                        Регистрация на сайте ↗
                    </a>
                ) : (
                    <Notice>Регистрация проходит у организатора.</Notice>
                );
        }
    };

    return (
        <aside className="flex h-fit w-full flex-col gap-[12px] lg:sticky lg:top-6 lg:w-[340px] lg:shrink-0">
            <div className="flex flex-col gap-3 rounded-2xl bg-cards-surface p-5 shadow-card">
                <div className="flex items-baseline justify-between gap-2">
                    <span className="text-h2 text-textprimary">{formatGoing(event.participants_count)}</span>
                    {seats !== null && (
                        <span className={`text-small ${seats === 0 ? "text-texterror" : "text-textsuccess"}`}>
                            {seats === 0 ? "мест нет" : `ещё ${formatSeats(seats)}`}
                        </span>
                    )}
                </div>
                {event.capacity !== null && (
                    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
                        <div
                            className="h-full rounded-full bg-gradient-to-r from-borderlight to-bordermain"
                            style={{ width: `${Math.min(100, (event.participants_count / event.capacity) * 100)}%` }}
                        />
                    </div>
                )}
                {renderAction()}
                {message && !error && <span className="text-small text-textsuccess">{message}</span>}
                {error && <Notice tone="error">{error}</Notice>}
            </div>

            {isOrganizer && requests.length > 0 && (
                <div className="flex flex-col gap-2 rounded-2xl bg-cards-surface p-5 shadow-card">
                    <h2 className="text-h3 text-textprimary">Заявки ({requests.length})</h2>
                    <PeopleList
                        emptyText=""
                        people={requests.map(({ user }) => ({
                            user,
                            actions: (
                                <>
                                    <button
                                        type="button"
                                        title="Принять"
                                        disabled={busy}
                                        onClick={() =>
                                            userId && run(() => reviewParticipation(event.id, user.id, userId, true), "Заявка принята.")
                                        }
                                        className="h-8 w-8 cursor-pointer rounded-lg bg-success/12 text-textsuccess transition hover:bg-success hover:text-textthird"
                                    >
                                        ✓
                                    </button>
                                    <button
                                        type="button"
                                        title="Отклонить"
                                        disabled={busy}
                                        onClick={() =>
                                            userId && run(() => reviewParticipation(event.id, user.id, userId, false), "Заявка отклонена.")
                                        }
                                        className="h-8 w-8 cursor-pointer rounded-lg bg-error/12 text-texterror transition hover:bg-error hover:text-textthird"
                                    >
                                        ✕
                                    </button>
                                </>
                            ),
                        }))}
                    />
                </div>
            )}

            <div className="flex flex-col gap-2 rounded-2xl bg-cards-surface p-5 shadow-card">
                <h2 className="text-h3 text-textprimary">Участники</h2>
                {participantsLoading && !participants ? (
                    <span className="text-small text-textsecondary">Загружаем…</span>
                ) : (
                    <PeopleList
                        emptyText="Пока никого — станьте первым!"
                        people={going.map(({ user, status }) => ({
                            user,
                            note: user.id === event.organizer?.id ? "организатор" : PARTICIPATION_LABELS[status].toLowerCase(),
                        }))}
                    />
                )}
            </div>
        </aside>
    );
};
