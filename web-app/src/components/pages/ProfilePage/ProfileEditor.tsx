import { useState } from "react";
import { errorText, getAccount, normalizeUsername, saveProfileWithAccount } from "../../../api";
import type { Profile } from "../../../models";
import { Button, FormField, Input, Notice, Textarea } from "../../ui";

export const ProfileEditor = ({ profile, editing, onEditingChange: setEditing, onSaved }: {
    profile: Profile;
    editing: boolean;
    onEditingChange: (editing: boolean) => void;
    onSaved: (profile: Profile) => void;
}) => {
    const [form, setForm] = useState({ username: profile.username, email: "", display_name: profile.display_name,
        bio: profile.bio ?? "", city: profile.city ?? "", latitude: profile.latitude ?? "", longitude: profile.longitude ?? "" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);
    const begin = async () => {
        setError(null); setSaved(false); setBusy(true);
        try {
            const account = await getAccount();
            if (account.id !== profile.id) throw new Error("Аккаунт изменился. Откройте свой профиль заново.");
            setForm({ username: account.username, email: account.email ?? "", display_name: profile.display_name, bio: profile.bio ?? "",
                city: profile.city ?? "", latitude: profile.latitude ?? "", longitude: profile.longitude ?? "" });
            setEditing(true);
        } catch (error) { setError(errorText(error)); } finally { setBusy(false); }
    };
    if (!editing) return <>
        <Button
            onClick={() => void begin()}
            disabled={busy}
            ariaLabel={busy ? "Загружаем аккаунт…" : "Редактировать профиль"}
            title="Редактировать профиль"
            className="absolute right-4 top-4 !h-[41px] !w-[41px] !px-0 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-borderfocus sm:right-8 sm:top-8"
        >
            {busy ? <span aria-hidden="true" className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : (
                <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m16 3 5 5M4 20l4-1L21 6a2.1 2.1 0 0 0-3-3L5 16l-1 4Z" />
                </svg>
            )}
        </Button>
        {saved && <Notice>Профиль сохранён.</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
    </>;
    const save = async (e: React.FormEvent) => {
        e.preventDefault(); setError(null);
        const username = normalizeUsername(form.username);
        if (!form.display_name.trim() || !/^[a-z0-9_]{3,50}$/.test(username)) {
            setError("Укажите имя и никнейм из 3–50 строчных латинских букв, цифр или символов _."); return;
        }
        const lat = form.latitude.trim().replace(",", ".");
        const lon = form.longitude.trim().replace(",", ".");
        if (Boolean(lat) !== Boolean(lon) || (lat && (!Number.isFinite(Number(lat)) || Math.abs(Number(lat)) > 90 || !Number.isFinite(Number(lon)) || Math.abs(Number(lon)) > 180))) {
            setError("Укажите обе координаты: широта от −90 до 90, долгота от −180 до 180."); return;
        }
        setBusy(true);
        try {
            const updated = await saveProfileWithAccount(profile.id, profile.username, { username, display_name: form.display_name.trim(),
                bio: form.bio.trim() || null, city: form.city.trim() || null,
                latitude: lat ? Number(lat).toFixed(6) : null, longitude: lon ? Number(lon).toFixed(6) : null }, form.email);
            onSaved(updated); setEditing(false); setSaved(true);
        } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
    };
    return <form onSubmit={save} className="flex w-full flex-col gap-4">
        <fieldset disabled={busy} className="flex flex-col gap-4">
            <FormField label="Имя" htmlFor="profile-name"><Input id="profile-name" required maxLength={120} value={form.display_name} onChange={(display_name) => setForm({ ...form, display_name })} /></FormField>
            <FormField label="Никнейм" htmlFor="profile-username" hint="Используется для входа в аккаунт."><Input id="profile-username" required minLength={3} maxLength={50} autoComplete="username" value={form.username} onChange={(username) => setForm({ ...form, username })} /></FormField>
            <FormField label="Почта" htmlFor="profile-email" hint="Необязательно. Можно использовать для входа; оставьте пустой, чтобы удалить."><Input id="profile-email" type="email" autoComplete="email" maxLength={254} value={form.email} onChange={(email) => setForm({ ...form, email })} /></FormField>
            <FormField label="О себе" htmlFor="profile-bio"><Textarea id="profile-bio" maxLength={2000} value={form.bio} onChange={(bio) => setForm({ ...form, bio })} /></FormField>
            <FormField label="Город" htmlFor="profile-city"><Input id="profile-city" maxLength={120} value={form.city} onChange={(city) => setForm({ ...form, city })} /></FormField>
            <FormField label="Широта" htmlFor="profile-lat"><Input id="profile-lat" inputMode="decimal" value={form.latitude} onChange={(latitude) => setForm({ ...form, latitude })} /></FormField>
            <FormField label="Долгота" htmlFor="profile-lon" hint="Оставьте обе координаты пустыми, чтобы удалить их."><Input id="profile-lon" inputMode="decimal" value={form.longitude} onChange={(longitude) => setForm({ ...form, longitude })} /></FormField>
            {error && <Notice tone="error">{error}</Notice>}
            <div className="flex gap-2"><Button type="submit">{busy ? "Сохраняем…" : "Сохранить профиль"}</Button><Button onClick={() => setEditing(false)}>Отмена</Button></div>
        </fieldset>
    </form>;
};
