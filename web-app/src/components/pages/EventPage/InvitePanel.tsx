import { useState } from "react";
import { errorText, inviteToEvent, listFriends } from "../../../api";
import { useAsync } from "../../../hooks";
import type { DvizhEvent, Participant } from "../../../models";
import { Button, Input, Notice } from "../../ui";
import { PeopleList } from "../../widgets";

interface InvitePanelProps {
    event: DvizhEvent;
    userId: string;
    participants: Participant[] | undefined;
}

/**
 * Приглашения друзей организатора. Backend разрешает приглашать только организатору
 * и менеджерам; приглашение не резервирует место.
 */
export const InvitePanel = ({ event, userId, participants }: InvitePanelProps) => {
    const friendsState = useAsync(() => listFriends(userId), userId);
    const [message, setMessage] = useState("");
    const [invited, setInvited] = useState<Set<string>>(() => new Set());
    const [busyId, setBusyId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const statusOf = (friendId: string) => participants?.find((p) => p.user.id === friendId)?.status;

    const invite = async (friendId: string) => {
        setBusyId(friendId);
        setError(null);
        try {
            await inviteToEvent(event.id, { actor_id: userId, invitee_id: friendId, message: message.trim() || null });
            setInvited((prev) => new Set(prev).add(friendId));
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusyId(null);
        }
    };

    const friends = friendsState.data ?? [];

    return (
        <div className="flex w-full flex-col gap-2.5 rounded-lg bg-cards-surface p-4">
            <h2 className="text-h2 text-textprimary">Пригласить друзей</h2>
            <p className="text-small text-textsecondary">
                Приглашённый увидит событие у себя в уведомлениях и сможет принять его, даже если вход только по приглашению.
            </p>
            {friendsState.loading ? (
                <span className="text-body text-textsecondary">Загрузка...</span>
            ) : friendsState.error !== undefined ? (
                <Notice tone="error">{errorText(friendsState.error)}</Notice>
            ) : (
                <>
                    {friends.length > 0 && (
                        <Input
                            placeholder="Сообщение к приглашению (необязательно)"
                            aria-label="Сообщение к приглашению"
                            maxLength={500}
                            value={message}
                            onChange={setMessage}
                        />
                    )}
                    <PeopleList
                        emptyText="Добавьте друзей, чтобы приглашать их на события."
                        people={friends.map((friend) => {
                            const status = statusOf(friend.id);
                            const done = invited.has(friend.id);
                            return {
                                user: friend,
                                avatarUrl: friend.avatar_url,
                                note: status === "GOING" ? "уже идёт" : status === "REQUESTED" ? "подал заявку" : done ? "приглашение отправлено" : undefined,
                                actions:
                                    status === "GOING" ? undefined : (
                                        <Button
                                            state={done ? "fixed1" : "hover2"}
                                            className="!h-[30px] !px-4"
                                            disabled={busyId !== null || done}
                                            onClick={() => invite(friend.id)}
                                        >
                                            {done ? "Приглашён" : "Пригласить"}
                                        </Button>
                                    ),
                            };
                        })}
                    />
                </>
            )}
            {error && <Notice tone="error">{error}</Notice>}
        </div>
    );
};
