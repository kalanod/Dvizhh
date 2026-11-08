import { useState } from "react";
import { errorText, inviteToEvent, listFriends, listEventInvitations, revokeInvitation } from "../../../api";
import { useAsync } from "../../../hooks";
import type { DvizhEvent, Participant } from "../../../models";
import { Button, FormField, Input, Notice } from "../../ui";
import { PeopleList } from "../../widgets";
import { formatAgo } from "../../../utils/format";

interface InvitePanelProps {
    event: DvizhEvent;
    userId: string;
    participants: Participant[] | undefined;
}

export const InvitePanel = ({ event, userId, participants }: InvitePanelProps) => {
    const friendsState = useAsync((signal) => listFriends(userId, signal), userId);
    const [limit, setLimit] = useState(20);
    const sent = useAsync((signal) => listEventInvitations(event.id, userId, { limit, signal }), `${event.id}:${userId}:${limit}`);
    const [message, setMessage] = useState("");
    const [expiresAt, setExpiresAt] = useState("");
    const [inviteeId, setInviteeId] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const run = async (action: () => Promise<unknown>, text: string) => {
        setBusy(true); setError(null); setSuccess(null);
        try { await action(); setSuccess(text); sent.reload(); }
        catch (err) { setError(errorText(err)); }
        finally { setBusy(false); }
    };
    const invite = (id: string) => run(async () => {
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id.trim())) throw new Error("Укажите корректный ID пользователя.");
        if (id.trim() === userId) throw new Error("Нельзя пригласить себя.");
        const expiry = expiresAt ? new Date(expiresAt) : null;
        if (expiry && (!Number.isFinite(expiry.getTime()) || expiry.getTime() <= Date.now())) throw new Error("Срок приглашения должен быть в будущем.");
        await inviteToEvent(event.id, { actor_id: userId, invitee_id: id.trim(), message: message.trim() || null, expires_at: expiry?.toISOString() ?? null });
    }, "Приглашение отправлено.");
    return <div className="flex w-full flex-col gap-4 rounded-lg bg-cards-surface p-4">
        <h2 className="text-h2 text-textprimary">Приглашения</h2>
        <fieldset disabled={busy} className="flex min-w-0 flex-col gap-4">
            <FormField label="Сообщение" htmlFor="invite-message"><Input id="invite-message" maxLength={500} value={message} onChange={setMessage} /></FormField>
            <FormField label="Действует до" htmlFor="invite-expiry" hint="Необязательно. Время в часовом поясе вашего устройства."><Input id="invite-expiry" type="datetime-local" value={expiresAt} onChange={setExpiresAt} /></FormField>
            <form onSubmit={(e) => { e.preventDefault(); void invite(inviteeId); }} className="flex flex-col gap-2">
                <FormField label="ID пользователя" htmlFor="invite-id" hint="Можно пригласить пользователя, которого нет в друзьях."><Input id="invite-id" required value={inviteeId} onChange={setInviteeId} /></FormField>
                <Button type="submit">Пригласить по ID</Button>
            </form>
            <h3 className="text-h3 text-textprimary">Друзья</h3>
            {friendsState.loading && <p>Загрузка друзей…</p>}
            {friendsState.error !== undefined && <Notice tone="error">{errorText(friendsState.error)}</Notice>}
            <PeopleList emptyText="Друзей пока нет. Вы можете отправить приглашение по ID." people={(friendsState.data ?? []).map((friend) => {
                const going = participants?.some((item) => item.user.id === friend.id && item.status === "GOING");
                return { user: friend, note: going ? "уже идёт" : undefined,
                    actions: !going && <Button onClick={() => void invite(friend.id)}>Пригласить</Button> };
            })} />
        </fieldset>
        {error && <Notice tone="error">{error}</Notice>}
        {success && <Notice>{success}</Notice>}
        <h3 className="text-h3 text-textprimary">Отправленные приглашения</h3>
        {sent.loading && <p>Загрузка приглашений…</p>}
        {sent.error !== undefined && <Notice tone="error">{errorText(sent.error)}</Notice>}
        {sent.data?.length === 0 && <p>Отправленных приглашений пока нет.</p>}
        {sent.data?.map((invitation) => {
            const expired = Boolean(invitation.expires_at && new Date(invitation.expires_at).getTime() <= Date.now());
            const status = expired && invitation.status === "PENDING" ? "EXPIRED" : invitation.status;
            const labels = { PENDING: "Ожидает ответа", ACCEPTED: "Принято", DECLINED: "Отклонено", REVOKED: "Отозвано", EXPIRED: "Срок истёк" };
            return <div key={invitation.id} className="flex flex-wrap items-center gap-2 rounded-lg border-2 border-borderlight p-3">
                <div className="min-w-0 flex-1 break-words"><a href={`/users/${invitation.invitee_user_id}`} className="underline">{friendsState.data?.find((friend) => friend.id === invitation.invitee_user_id)?.display_name ?? invitation.invitee_user_id}</a>
                    <p>{labels[status]} · {formatAgo(invitation.created_at)}</p>
                    {invitation.message && <p>{invitation.message}</p>}
                    {invitation.expires_at && <p>До {new Date(invitation.expires_at).toLocaleString("ru-RU")}</p>}
                </div>
                {status === "PENDING" && <Button disabled={busy} onClick={() => void run(() => revokeInvitation(invitation.id, userId), "Приглашение отозвано.")}>Отозвать</Button>}
            </div>;
        })}
        {(sent.data?.length ?? 0) >= limit && <Button disabled={sent.loading || busy} onClick={() => setLimit((value) => value + 20)}>Показать ещё приглашения</Button>}
    </div>;
};
