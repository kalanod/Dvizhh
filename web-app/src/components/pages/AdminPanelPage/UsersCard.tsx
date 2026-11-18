import { useEffect, useRef, useState } from "react";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import { ApiError, errorText } from "../../../api/client";
import { searchAdminUsers, changeAdminUserRole, type AdminUsersPage } from "../../../api/adminUsers";
import type { AccountRole, CurrentAccount } from "../../../api/auth";
import type { SettingsCard } from "../../../models/settings";
import { useCurrentUser } from "../../../hooks";
import { Button, Input, Loader, Notice, Select } from "../../ui";
import { UserPasswordDialog } from "./UserPasswordDialog";

const roles: Record<AccountRole, string> = { user: "Пользователь", admin: "Администратор" };

export function UsersCard({ card, onAccessLost }: { card: SettingsCard; onAccessLost: () => void }) {
    const { userId } = useCurrentUser();
    const [query, setQuery] = useState("");
    const [offset, setOffset] = useState(0);
    const [revision, setRevision] = useState(0);
    const [result, setResult] = useState<{ key: string; page?: AdminUsersPage; error?: unknown }>();
    const [edits, setEdits] = useState<Record<string, AccountRole>>({});
    const [busy, setBusy] = useState<string | null>(null);
    const [feedback, setFeedback] = useState<{ id: string; text: string; error?: boolean } | null>(null);
    const [passwordAccount, setPasswordAccount] = useState<CurrentAccount | null>(null);
    const saving = useRef(false);
    const key = JSON.stringify([query.trim(), offset, revision]);
    const onAccessLostRef = useRef(onAccessLost);
    useEffect(() => { onAccessLostRef.current = onAccessLost; }, [onAccessLost]);
    useEffect(() => {
        const controller = new AbortController();
        const [text, pageOffset] = JSON.parse(key) as [string, number, number];
        const timer = window.setTimeout(() => {
            void searchAdminUsers(text, pageOffset, controller.signal).then((page) => {
                if (!controller.signal.aborted) setResult({ key, page });
            }).catch((error: unknown) => {
                if (controller.signal.aborted) return;
                setResult({ key, error });
                if (error instanceof ApiError && [401, 403].includes(error.status)) onAccessLostRef.current();
            });
        }, text ? 300 : 0);
        return () => { window.clearTimeout(timer); controller.abort(); };
    }, [key]);
    const current = result?.key === key ? result : undefined;
    const accessError = (error: unknown) => {
        if (error instanceof ApiError && [401, 403].includes(error.status)) onAccessLost();
    };
    const saveRole = async (account: CurrentAccount) => {
        const role = edits[account.id];
        if (!role || role === account.role || saving.current) return;
        saving.current = true; setBusy(account.id); setFeedback(null);
        try {
            await changeAdminUserRole(account.id, role);
            setEdits((previous) => { const next = { ...previous }; delete next[account.id]; return next; });
            setRevision((previous) => previous + 1);
            setFeedback({ id: account.id, text: "Роль сохранена." });
        } catch (error) { setFeedback({ id: account.id, text: errorText(error), error: true }); accessError(error); }
        finally { saving.current = false; setBusy(null); }
    };
    return <article data-settings-card={card.id} className="min-w-0 rounded-lg bg-cards-surface p-4 sm:p-5">
        <h2 className="mb-4 text-h2 text-textprimary">{card.title ?? "Пользователи"}</h2>
        <Input id="admin-users-search" aria-label="Поиск пользователей" placeholder="Никнейм или почта" type="search" maxLength={120}
            value={query} disabled={!!busy} onChange={(value) => { setQuery(value); setOffset(0); setEdits({}); setFeedback(null); }} />
        <div className="mt-4" aria-live="polite" aria-busy={!current}>
            {!current ? <Loader text="Загружаем пользователей…" /> : current.error ? <div className="flex flex-col items-start gap-3">
                <Notice tone="error">{errorText(current.error)}</Notice>
                <Button onClick={() => setRevision((previous) => previous + 1)}>Повторить загрузку</Button>
            </div> : !current.page?.items.length ? <div className="flex flex-col items-start gap-3">
                <Notice>{offset ? "На этой странице больше нет пользователей." : query.trim() ? "Пользователи не найдены." : "Пользователей пока нет."}</Notice>
                {offset > 0 && <Button state="hover2" onClick={() => setOffset(Math.max(0, offset - 20))}>Назад</Button>}
            </div> : <>
                <div className="overflow-x-auto">
                    <Table aria-label="Пользователи" sx={{ minWidth: 620, "& .MuiTableCell-root": { fontFamily: "inherit", color: "var(--color-textprimary)", borderColor: "var(--color-borderlight)", px: 1.5, verticalAlign: "top" } }}>
                        <TableHead><TableRow><TableCell>Пользователь</TableCell><TableCell>Роль</TableCell><TableCell>Действия</TableCell></TableRow></TableHead>
                        <TableBody>{current.page.items.map((account) => <TableRow key={account.id}>
                            <TableCell component="th" scope="row" sx={{ maxWidth: 240, overflowWrap: "anywhere" }}>
                                <div className="font-medium">@{account.username}{account.id === userId ? " · вы" : ""}</div>
                                <div className="text-small text-textsecondary">{account.email || "Почта не указана"}</div>
                            </TableCell>
                            <TableCell>
                                <div className="flex min-w-44 flex-col items-start gap-2">
                                    <Select<AccountRole> aria-label={`Роль @${account.username}`} value={edits[account.id] ?? account.role}
                                        options={roles} disabled={!!busy || account.id === userId} onChange={(value) => setEdits((previous) => ({ ...previous, [account.id]: value }))} />
                                    <Button disabled={!!busy || !edits[account.id] || edits[account.id] === account.role} onClick={() => void saveRole(account)}>{busy === account.id ? "Сохраняем…" : "Сохранить роль"}</Button>
                                </div>
                            </TableCell>
                            <TableCell>
                                <Button disabled={!!busy} onClick={() => { setFeedback(null); setPasswordAccount(account); }}>Сменить пароль</Button>
                                {feedback?.id === account.id && <Notice className="mt-2" tone={feedback.error ? "error" : "success"}>{feedback.text}</Notice>}
                            </TableCell>
                        </TableRow>)}</TableBody>
                    </Table>
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                    <p className="text-small text-textsecondary">Страница {Math.floor(offset / 20) + 1}</p>
                    <div className="flex gap-2">
                        <Button state="hover2" disabled={!!busy || offset === 0} onClick={() => { setOffset(offset - 20); setEdits({}); setFeedback(null); }}>Назад</Button>
                        <Button state="hover2" disabled={!!busy || !current.page.has_more} onClick={() => { setOffset(offset + 20); setEdits({}); setFeedback(null); }}>Далее</Button>
                    </div>
                </div>
            </>}
        </div>
        {passwordAccount && <UserPasswordDialog key={passwordAccount.id} account={passwordAccount} onClose={() => setPasswordAccount(null)}
            onSaved={() => { setFeedback({ id: passwordAccount.id, text: "Пароль изменён." }); setPasswordAccount(null); }} onError={accessError} />}
    </article>;
}
