import type { ReactNode } from "react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
    errorText,
    listFriendRequests,
    listInvitations,
    listNotifications,
    markNotificationRead,
    mediaSrc,
    respondToFriendship,
    respondToInvitation,
} from "../../../api";
import { notifyInboxChanged, useAsync, useCurrentUser } from "../../../hooks";
import type { DvizhNotification, InvitationCard } from "../../../models";
import { MainLayout } from "../../layouts";
import { Avatar, Button, Loader, Notice } from "../../ui";
import { EventCard, LoginRequired } from "../../widgets";
import { formatAgo, formatChangedFields, formatEventDate } from "../../../utils/format";

const PAGE_SIZE = 20;
const MAX_LIMIT = 100;

export const NotificationsPage = () => {
    const { userId, loading } = useCurrentUser();

    return (
        <MainLayout>
            {loading ? (
                <Loader />
            ) : userId ? (
                <div className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
                    <h1 className="text-h1 text-textthird">Уведомления</h1>
                    <InvitationsBlock userId={userId} />
                    <FriendRequestsBlock userId={userId} />
                    <EventNotificationsBlock userId={userId} />
                </div>
            ) : (
                <LoginRequired text="Войдите, чтобы видеть уведомления и приглашения" />
            )}
        </MainLayout>
    );
};

const Block = ({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) => (
    <section className="flex w-full flex-col gap-[10px] rounded-lg bg-cards-surface p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-h2 text-textprimary">{title}</h2>
            {action}
        </div>
        {children}
    </section>
);

/** Выполняет действие и показывает результат или ошибку; общий шаблон для кнопок блоков. */
const useAction = (onDone: () => void) => {
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const run = async (action: () => Promise<unknown>) => {
        setBusy(true);
        setError(null);
        try {
            await action();
            onDone();
            notifyInboxChanged();
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    };

    return { busy, error, run };
};

const InvitationsBlock = ({ userId }: { userId: string }) => {
    const state = useAsync((signal) => listInvitations(userId, { limit: MAX_LIMIT, signal }), userId);
    const { busy, error, run } = useAction(state.reload);
    const invitations = state.data ?? [];

    return (
        <Block title={`Приглашения${invitations.length > 0 ? ` (${invitations.length})` : ""}`}>
            {state.loading && !state.data && <span className="text-body text-textsecondary">Загрузка...</span>}
            {state.error !== undefined && <Notice tone="error">{errorText(state.error)}</Notice>}
            {error && <Notice tone="error">{error}</Notice>}
            {!state.loading && !state.error && invitations.length === 0 && (
                <p className="text-body text-textsecondary">Новых приглашений нет.</p>
            )}
            {invitations.map((card) => (
                <InvitationRow
                    key={card.invitation.id}
                    card={card}
                    busy={busy}
                    onRespond={(accept) => run(() => respondToInvitation(card.invitation.id, userId, accept))}
                />
            ))}
        </Block>
    );
};

const InvitationRow = ({ card, busy, onRespond }: { card: InvitationCard; busy: boolean; onRespond: (accept: boolean) => void }) => {
    const { invitation, event } = card;

    return (
        <div className="flex w-full flex-col gap-2 rounded-lg border-2 border-borderlight p-2 sm:p-3">
            {invitation.message && (
                <p className="text-body whitespace-pre-line text-textprimary">
                    <span className="text-textsecondary">Сообщение: </span>
                    {invitation.message}
                </p>
            )}
            <EventCard event={event} />
            <div className="flex flex-wrap items-center gap-2">
                <Button state="hover2" className="!h-[30px] !px-4" disabled={busy} onClick={() => onRespond(true)}>
                    Принять — иду
                </Button>
                <Button state="hover1" className="!h-[30px] !px-4" disabled={busy} onClick={() => onRespond(false)}>
                    Отклонить
                </Button>
                <span className="text-small text-textsecondary">
                    {formatAgo(invitation.created_at)}
                    {invitation.expires_at && ` · действует до ${formatEventDate({ starts_at: invitation.expires_at, ends_at: null, is_all_day: false, timezone: event.timezone })}`}
                </span>
            </div>
        </div>
    );
};

const FriendRequestsBlock = ({ userId }: { userId: string }) => {
    const navigate = useNavigate();
    const incoming = useAsync((signal) => listFriendRequests(userId, "incoming", { limit: MAX_LIMIT, signal }), `${userId}:in`);
    const outgoing = useAsync((signal) => listFriendRequests(userId, "outgoing", { limit: MAX_LIMIT, signal }), `${userId}:out`);
    const { busy, error, run } = useAction(() => {
        incoming.reload();
        outgoing.reload();
    });
    const requests = incoming.data ?? [];
    const sent = outgoing.data ?? [];

    return (
        <Block title={`Заявки в друзья${requests.length > 0 ? ` (${requests.length})` : ""}`}>
            {incoming.loading && !incoming.data && <span className="text-body text-textsecondary">Загрузка...</span>}
            {incoming.error !== undefined && <Notice tone="error">{errorText(incoming.error)}</Notice>}
            {error && <Notice tone="error">{error}</Notice>}
            {!incoming.loading && !incoming.error && requests.length === 0 && (
                <p className="text-body text-textsecondary">Новых заявок нет.</p>
            )}
            {requests.map(({ user, friendship }) => (
                <PersonRow
                    key={user.id}
                    name={user.display_name}
                    username={user.username}
                    avatar={mediaSrc(user.avatar_url, userId)}
                    note={formatAgo(friendship.requested_at)}
                    onOpen={() => navigate(`/users/${user.id}`)}
                >
                    <Button
                        state="hover2"
                        className="!h-[30px] !px-4"
                        disabled={busy}
                        onClick={() => run(() => respondToFriendship(userId, user.id, true))}
                    >
                        Принять
                    </Button>
                    <Button
                        state="hover1"
                        className="!h-[30px] !px-4"
                        disabled={busy}
                        onClick={() => run(() => respondToFriendship(userId, user.id, false))}
                    >
                        Отклонить
                    </Button>
                </PersonRow>
            ))}

            {sent.length > 0 && (
                <>
                    <h3 className="mt-2 text-h3 text-textsecondary">Вы отправили ({sent.length})</h3>
                    {sent.map(({ user, friendship }) => (
                        <PersonRow
                            key={user.id}
                            name={user.display_name}
                            username={user.username}
                            avatar={mediaSrc(user.avatar_url, userId)}
                            note={`ждёт ответа · ${formatAgo(friendship.requested_at)}`}
                            onOpen={() => navigate(`/users/${user.id}`)}
                        />
                    ))}
                </>
            )}
        </Block>
    );
};

interface PersonRowProps {
    name: string;
    username: string;
    avatar: string | null;
    note: string;
    onOpen: () => void;
    children?: ReactNode;
}

const PersonRow = ({ name, username, avatar, note, onOpen, children }: PersonRowProps) => (
    <div className="flex min-h-[42px] w-full flex-wrap items-center gap-2.5 rounded-lg bg-primary p-2.5">
        <div className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5" onClick={onOpen}>
            <Avatar name={name} src={avatar} size="sm" />
            <span className="truncate text-body text-black">{name}</span>
            <span className="truncate text-duration text-textsecondary">
                @{username} · {note}
            </span>
        </div>
        {children && <div className="flex shrink-0 gap-1.5">{children}</div>}
    </div>
);

const EventNotificationsBlock = ({ userId }: { userId: string }) => {
    const navigate = useNavigate();
    const [unreadOnly, setUnreadOnly] = useState(false);
    const [limit, setLimit] = useState(PAGE_SIZE);
    const state = useAsync((signal) => listNotifications(userId, { unreadOnly, limit, signal }), `${userId}:${unreadOnly}:${limit}`);
    const { busy, error, run } = useAction(state.reload);
    const notifications = state.data ?? [];
    const unread = notifications.filter((item) => !item.read_at);
    const hasMore = notifications.length >= limit && limit < MAX_LIMIT;

    const open = async (item: DvizhNotification) => {
        if (!item.read_at) {
            // Переход важнее отметки: если она не удалась, счётчик просто обновится позже.
            await markNotificationRead(userId, item.id).catch(() => undefined);
            notifyInboxChanged();
        }
        navigate(`/events/${item.event_id}`);
    };

    const markAll = () => run(() => Promise.all(unread.map((item) => markNotificationRead(userId, item.id))));

    return (
        <Block
            title="Изменения в событиях"
            action={
                <div className="flex flex-wrap gap-2">
                    <Button
                        state={unreadOnly ? "fixed1" : "hover1"}
                        className="!h-[30px] !px-4"
                        ariaPressed={unreadOnly}
                        onClick={() => {
                            setLimit(PAGE_SIZE);
                            setUnreadOnly((value) => !value);
                        }}
                    >
                        Только непрочитанные
                    </Button>
                    {unread.length > 0 && (
                        <Button state="hover2" className="!h-[30px] !px-4" disabled={busy} onClick={markAll}>
                            Прочитать все
                        </Button>
                    )}
                </div>
            }
        >
            <p className="text-small text-textsecondary">
                Приходят, когда меняется или отменяется событие, на которое вы идёте, подали заявку, приглашены или сохранили.
            </p>
            {state.error !== undefined && <Notice tone="error">{errorText(state.error)}</Notice>}
            {error && <Notice tone="error">{error}</Notice>}
            {!state.loading && !state.error && notifications.length === 0 && (
                <p className="text-body text-textsecondary">{unreadOnly ? "Всё прочитано." : "Уведомлений пока нет."}</p>
            )}
            {notifications.map((item) => (
                <NotificationRow key={item.id} item={item} onOpen={() => open(item)} />
            ))}
            {state.loading && <span className="text-body text-textsecondary">Загрузка...</span>}
            {hasMore && !state.loading && (
                <Button state="hover1" className="self-center" onClick={() => setLimit((value) => Math.min(value + PAGE_SIZE, MAX_LIMIT))}>
                    Показать ещё
                </Button>
            )}
        </Block>
    );
};

const NotificationRow = ({ item, onOpen }: { item: DvizhNotification; onOpen: () => void }) => {
    const title = item.payload.title ?? "Событие";
    const cancelled = item.kind === "EVENT_CANCELLED";
    const changes = formatChangedFields(item.payload.changed_fields);

    return (
        <button
            type="button"
            onClick={onOpen}
            className={`flex w-full cursor-pointer items-start gap-2.5 rounded-lg border-2 p-2.5 text-left transition-all hover:shadow-hover ${
                item.read_at ? "border-transparent bg-primary/60" : "border-borderfocus bg-primary"
            }`}
        >
            <span
                aria-hidden="true"
                className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${item.read_at ? "bg-transparent" : cancelled ? "bg-error" : "bg-borderfocus"}`}
            />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className={`text-body break-words ${cancelled ? "text-texterror" : "text-textprimary"}`}>
                    {cancelled ? `Событие «${title}» отменено` : `В событии «${title}» изменения`}
                </span>
                {!cancelled && changes && <span className="text-small text-textsecondary">Изменилось: {changes}</span>}
            </span>
            <span className="shrink-0 text-small text-textsecondary">
                {!item.read_at && <span className="sr-only">Не прочитано. </span>}
                {formatAgo(item.created_at)}
            </span>
        </button>
    );
};
