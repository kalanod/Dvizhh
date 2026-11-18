import { useRef, useState } from "react";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import { errorText } from "../../../api/client";
import { resetAdminUserPassword } from "../../../api/adminUsers";
import type { CurrentAccount } from "../../../api/auth";
import { Button, FormField, Input, Notice } from "../../ui";

export function UserPasswordDialog({ account, onClose, onSaved, onError }: {
    account: CurrentAccount; onClose: () => void; onSaved: () => void;
    onError: (error: unknown) => void;
}) {
    const [password, setPassword] = useState("");
    const [confirmation, setConfirmation] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const submitting = useRef(false);
    const submit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        if (submitting.current) return;
        if (!event.currentTarget.reportValidity()) return;
        submitting.current = true; setBusy(true); setError(null);
        try {
            await resetAdminUserPassword(account.id, password);
            onSaved();
        } catch (failure) { setError(errorText(failure)); onError(failure); }
        finally { submitting.current = false; setBusy(false); setPassword(""); setConfirmation(""); }
    };
    return <Dialog open onClose={() => { if (!submitting.current) onClose(); }}
        aria-labelledby="user-password-title" maxWidth="sm" fullWidth
        slotProps={{ paper: { sx: { m: 2, borderRadius: "12px", backgroundColor: "var(--color-cards-surface)", color: "var(--color-textprimary)", fontFamily: "inherit" } } }}>
        <DialogTitle id="user-password-title" sx={{ fontFamily: "inherit", overflowWrap: "anywhere" }}>Сменить пароль @{account.username}</DialogTitle>
        <DialogContent>
            <form noValidate onSubmit={(event) => void submit(event)} className="flex flex-col gap-4 pt-2">
                <FormField label="Новый пароль" htmlFor="admin-new-password" required>
                    <Input autoFocus id="admin-new-password" type="password" autoComplete="new-password"
                        minLength={8} maxLength={128} value={password} onChange={setPassword} disabled={busy} errorDisplay="inline" />
                </FormField>
                <FormField label="Повторите пароль" htmlFor="admin-confirm-password" required>
                    <Input id="admin-confirm-password" type="password" autoComplete="new-password"
                        maxLength={128} value={confirmation} onChange={setConfirmation} disabled={busy} errorDisplay="inline"
                        validate={(value) => value === password ? null : "Пароли не совпадают."} />
                </FormField>
                {error && <Notice tone="error">{error}</Notice>}
                <div className="flex flex-wrap justify-end gap-2">
                    <Button onClick={onClose} disabled={busy} state="hover2">Отмена</Button>
                    <Button type="submit" disabled={busy}>{busy ? "Сохраняем…" : "Сменить пароль"}</Button>
                </div>
            </form>
        </DialogContent>
    </Dialog>;
}
