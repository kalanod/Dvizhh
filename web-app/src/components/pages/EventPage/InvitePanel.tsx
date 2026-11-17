import { useState } from "react";
import { errorText, inviteToEvent, listEventInvitations, revokeInvitation } from "../../../api";
import { useAsync } from "../../../hooks";
import type { DvizhEvent, Participant, Profile } from "../../../models";
import { Button, Notice } from "../../ui";
import { formatAgo } from "../../../utils/format";
import { FriendPicker } from "./FriendPicker";

interface InvitePanelProps {
    event: DvizhEvent;
    userId: string;
    participants: Participant[] | undefined;
}

export const InvitePanel = ({ event, userId, participants }: InvitePanelProps) => {
    const [limit, setLimit] = useState(20);
    const sent = useAsync((signal) => listEventInvitations(event.id, userId, { limit, signal }), `${event.id}:${userId}:${limit}`);
    const [friend, setFriend] = useState<Profile | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const unavailable = (id: string) => participants?.some((item) => item.user.id === id && item.status === "GOING")
        ? "Уже идёт" : sent.data?.some((invitation) => invitation.invitee_user_id === id && invitation.status === "PENDING")
            ? "Приглашение уже отправлено" : undefined;
    const run = async (action: () => Promise<unknown>, text: string) => {
        if (busy) return;
        setBusy(true); setError(null); setSuccess(null);
        try { await action(); setSuccess(text); sent.reload(); }
        catch (err) { setError(errorText(err)); }
        finally { setBusy(false); }
    };
    const invite = () => {
        if (!friend || unavailable(friend.id)) return;
        void run(async () => {
            await inviteToEvent(event.id, { actor_id: userId, invitee_id: friend.id });
            setFriend(null);
        }, "Приглашение отправлено.");
    };
    const labels = { PENDING: "Ожидает ответа", ACCEPTED: "Принято", DECLINED: "Отклонено", REVOKED: "Отозвано", EXPIRED: "Срок истёк" };
    return <div className="flex w-full flex-col gap-4 rounded-lg bg-cards-surface p-4">
        <h2 className="text-h2 text-textprimary">Пригласить друга</h2>
        <form onSubmit={(event) => { event.preventDefault(); invite(); }} className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start">
            <FriendPicker userId={userId} value={friend} onChange={setFriend} disabled={busy} unavailable={unavailable} />
            <Button type="submit" className="!h-14" disabled={busy || !friend || Boolean(friend && unavailable(friend.id))}>
                {busy ? "Отправляем…" : "Пригласить"}
            </Button>
        </form>
        {error && <Notice tone="error">{error}</Notice>}
        {success && <Notice>{success}</Notice>}
        <h3 className="text-h3 text-textprimary">Отправленные приглашения</h3>
        {sent.loading && <p>Загрузка приглашений…</p>}
        {sent.error !== undefined && <Notice tone="error">{errorText(sent.error)}</Notice>}
        {sent.data?.length === 0 && <p>Отправленных приглашений пока нет.</p>}
        {sent.data?.map((invitation) => <div key={invitation.id} className="flex flex-wrap items-center gap-2 rounded-lg border-2 border-borderlight p-3">
            <div className="min-w-0 flex-1 break-words">
                <a href={`/users/${invitation.invitee_user_id}`} className="underline">{invitation.invitee_name ?? "Пользователь"}</a>
                <p>{labels[invitation.status]} · {formatAgo(invitation.created_at)}</p>
            </div>
            {invitation.status === "PENDING" && <Button disabled={busy} onClick={() => void run(() => revokeInvitation(invitation.id, userId), "Приглашение отозвано.")}>Отозвать</Button>}
        </div>)}
        {(sent.data?.length ?? 0) >= limit && <Button disabled={sent.loading || busy} onClick={() => setLimit((value) => value + 20)}>Показать ещё приглашения</Button>}
    </div>;
};