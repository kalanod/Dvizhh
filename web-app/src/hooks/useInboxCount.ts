import { useEffect, useState } from "react";
import { listFriendRequests, listInvitations, listNotifications } from "../api";

const INBOX_CHANGED = "dvizh:inbox-changed";
const POLL_MS = 60_000;
// Списки backend-а отдают максимум 100 записей — для счётчика этого хватает.
const MAX = 100;

/** Сообщить счётчику в шапке, что входящие изменились (прочитали, приняли приглашение и т. п.). */
export const notifyInboxChanged = () => window.dispatchEvent(new Event(INBOX_CHANGED));

const loadCount = async (userId: string) => {
    const [notifications, invitations, requests] = await Promise.all([
        listNotifications(userId, { unreadOnly: true, limit: MAX }),
        listInvitations(userId, { limit: MAX }),
        listFriendRequests(userId, "incoming", { limit: MAX }),
    ]);
    return notifications.length + invitations.length + requests.length;
};

/**
 * Сколько всего ждёт внимания: непрочитанные уведомления, приглашения и заявки в друзья.
 * Push/WebSocket backend пока не даёт, поэтому счётчик опрашивается раз в минуту.
 */
export const useInboxCount = (userId: string | null) => {
    const [count, setCount] = useState<{ userId: string; value: number } | null>(null);

    useEffect(() => {
        if (!userId) return;
        let cancelled = false;
        const load = () => {
            loadCount(userId).then(
                (value) => !cancelled && setCount({ userId, value }),
                () => undefined, // Счётчик необязателен: при ошибке остаётся прежнее значение.
            );
        };
        load();
        const timer = window.setInterval(load, POLL_MS);
        window.addEventListener(INBOX_CHANGED, load);
        return () => {
            cancelled = true;
            window.clearInterval(timer);
            window.removeEventListener(INBOX_CHANGED, load);
        };
    }, [userId]);

    return count?.userId === userId ? count.value : 0;
};
