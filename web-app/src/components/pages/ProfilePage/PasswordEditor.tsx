import { useState } from "react";
import { changePassword, errorText } from "../../../api";
import { Button, FormField, Input, Notice } from "../../ui";

export const PasswordEditor = () => {
    const [editing, setEditing] = useState(false);
    const [form, setForm] = useState({ current: "", next: "", confirmation: "" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);
    const reset = () => { setForm({ current: "", next: "", confirmation: "" }); setEditing(false); setError(null); };
    const save = async (event: React.FormEvent) => {
        event.preventDefault(); setError(null); setSaved(false);
        if (form.next !== form.confirmation) { setError("Новые пароли не совпадают."); return; }
        setBusy(true);
        try {
            await changePassword({ current_password: form.current, new_password: form.next });
            reset(); setSaved(true);
        } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
    };
    if (!editing) return <div>
        <Button onClick={() => { setSaved(false); setEditing(true); }}>Сменить пароль</Button>
        {saved && <Notice>Пароль изменён.</Notice>}
    </div>;
    return <form onSubmit={save} className="flex w-full flex-col gap-4">
        <fieldset disabled={busy} className="flex min-w-0 flex-col gap-4">
            <FormField label="Текущий пароль" htmlFor="password-current">
                <Input id="password-current" type="password" required maxLength={128} autoComplete="current-password" value={form.current} onChange={(current) => setForm({ ...form, current })} />
            </FormField>
            <FormField label="Новый пароль" htmlFor="password-new" hint="От 8 до 128 символов. Сервер может требовать более длинный пароль.">
                <Input id="password-new" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={form.next} onChange={(next) => setForm({ ...form, next })} />
            </FormField>
            <FormField label="Повторите новый пароль" htmlFor="password-confirmation">
                <Input id="password-confirmation" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={form.confirmation} onChange={(confirmation) => setForm({ ...form, confirmation })} />
            </FormField>
            {error && <Notice tone="error">{error}</Notice>}
            <div className="flex flex-wrap gap-2">
                <Button type="submit">{busy ? "Сохраняем…" : "Сохранить пароль"}</Button>
                <Button onClick={reset}>Отмена</Button>
            </div>
        </fieldset>
    </form>;
};
