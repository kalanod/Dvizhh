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

/** Участие текущего пользователя, заявки и список участников. */
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
                <Button state="hover1" onClick={() => navigate(`/login?next=/events/${event.id}`)}>
                    Войти, чтобы пойти
                </Button>
            );
        }
        if (myStatus === "GOING") {
            return (
                <>
                    <span className="text-h3 text-textsuccess">Вы идёте! Событие уже в вашем календаре.</span>
                    <Button state="hover1" disabled={busy} onClick={() => run(() => leaveEvent(event.id, userId), "Участие отменено.")}>
                        Отменить участие
                    </Button>
                </>
            );
        }
        if (myStatus === "REQUESTED") {
            return (
                <>
                    <span className="text-h3 text-textprimary">Заявка отправлена — ждём решения организатора.</span>
                    <Button state="hover1" disabled={busy} onClick={() => run(() => leaveEvent(event.id, userId), "Заявка отозвана.")}>
                        Отозвать заявку
                    </Button>
                </>
            );
        }
        switch (event.join_policy) {
            case "OPEN":
                return (
                    <Button
                        state="hover2"
                        disabled={busy || seats === 0}
                        onClick={() => run(() => joinEvent(event.id, userId), "Готово, вы в списке участников!")}
                    >
                        {seats === 0 ? "Мест нет" : "Иду"}
                    </Button>
                );
            case "REQUEST":
                return (
                    <Button
                        state="hover2"
                        disabled={busy || seats === 0}
                        onClick={() => run(() => joinEvent(event.id, userId), "Заявка отправлена организатору.")}
                    >
                        {seats === 0 ? "Мест нет" : "Подать заявку"}
                    </Button>
                );
            case "INVITE_ONLY":
                return <span className="text-h3 text-textprimary">Попасть можно только по приглашению организатора.</span>;
            case "EXTERNAL":
                return event.registration_url ? (
                    <a
                        href={event.registration_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-[41px] w-fit items-center justify-center rounded-lg border-2 border-borderlight bg-bordermain px-[23px] text-buttons text-textthird transition-all hover:shadow-hover"
                    >
                        Регистрация на сайте ↗
                    </a>
                ) : (
                    <span className="text-h3 text-textprimary">Регистрация проходит у организатора.</span>
                );
        }
    };

    return (
        <div className="flex w-full flex-col gap-[10px]">
            <div className="flex w-full flex-wrap items-center gap-2.5 rounded-lg bg-cards-surface p-4">
                <div className="flex flex-1 flex-col gap-1">
                    <span className="text-h2 text-textprimary">{formatGoing(event.participants_count)}</span>
                    {seats !== null && (
                        <span className={`text-duration ${seats === 0 ? "text-texterror" : "text-textsuccess"}`}>
                            {seats === 0 ? "мест нет" : `ещё ${formatSeats(seats)} из ${event.capacity}`}
                        </span>
                    )}
                </div>
                <div className="flex flex-wrap items-center gap-2.5">{renderAction()}</div>
                {message && !error && <span className="w-full text-small text-textsuccess">{message}</span>}
                {error && <Notice tone="error">{error}</Notice>}
            </div>

            {isOrganizer && requests.length > 0 && (
                <div className="flex w-full flex-col gap-2.5 rounded-lg bg-cards-surface p-4">
                    <h2 className="text-h2 text-textprimary">Заявки ({requests.length})</h2>
                    <PeopleList
                        emptyText=""
                        people={requests.map(({ user }) => ({
                            user,
                            actions: (
                                <>
                                    <Button
                                        state="hover2"
                                        className="!h-[30px] !px-4"
                                        disabled={busy}
                                        onClick={() =>
                                            userId && run(() => reviewParticipation(event.id, user.id, userId, true), "Заявка принята.")
                                        }
                                    >
                                        Принять
                                    </Button>
                                    <Button
                                        state="hover1"
                                        className="!h-[30px] !px-4"
                                        disabled={busy}
                                        onClick={() =>
                                            userId && run(() => reviewParticipation(event.id, user.id, userId, false), "Заявка отклонена.")
                                        }
                                    >
                                        Отклонить
                                    </Button>
                                </>
                            ),
                        }))}
                    />
                </div>
            )}

            <div className="flex w-full flex-col gap-2.5 rounded-lg bg-cards-surface p-4">
                <h2 className="text-h2 text-textprimary">Участники</h2>
                {participantsLoading && !participants ? (
                    <span className="text-body text-textsecondary">Загрузка...</span>
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
        </div>
    );
};
