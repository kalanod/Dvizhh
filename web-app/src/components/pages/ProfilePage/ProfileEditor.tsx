import { useState } from "react";
import { errorText, updateProfile } from "../../../api";
import type { Profile } from "../../../models";
import { Button, FormField, Input, Notice, Textarea } from "../../ui";

export const ProfileEditor = ({ profile, onSaved }: { profile: Profile; onSaved: (profile: Profile) => void }) => {
    const [editing, setEditing] = useState(false);
    const [form, setForm] = useState({ username: profile.username, display_name: profile.display_name,
        bio: profile.bio ?? "", city: profile.city ?? "", latitude: profile.latitude ?? "", longitude: profile.longitude ?? "" });
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saved, setSaved] = useState(false);
    const begin = () => {
        setForm({ username: profile.username, display_name: profile.display_name, bio: profile.bio ?? "",
            city: profile.city ?? "", latitude: profile.latitude ?? "", longitude: profile.longitude ?? "" });
        setError(null); setSaved(false); setEditing(true);
    };
    if (!editing) return <div><Button onClick={begin}>Редактировать профиль</Button>{saved && <Notice>Профиль сохранён.</Notice>}</div>;
    const save = async (e: React.FormEvent) => {
        e.preventDefault(); setError(null);
        if (!form.display_name.trim() || !/^[a-z0-9_]{3,50}$/.test(form.username.trim())) {
            setError("Укажите имя и никнейм из 3–50 строчных латинских букв, цифр или символов _."); return;
        }
        const lat = form.latitude.trim().replace(",", ".");
        const lon = form.longitude.trim().replace(",", ".");
        if (Boolean(lat) !== Boolean(lon) || (lat && (!Number.isFinite(Number(lat)) || Math.abs(Number(lat)) > 90 || !Number.isFinite(Number(lon)) || Math.abs(Number(lon)) > 180))) {
            setError("Укажите обе координаты: широта от −90 до 90, долгота от −180 до 180."); return;
        }
        setBusy(true);
        try {
            const updated = await updateProfile(profile.id, { username: form.username.trim(), display_name: form.display_name.trim(),
                bio: form.bio.trim() || null, city: form.city.trim() || null,
                latitude: lat ? Number(lat).toFixed(6) : null, longitude: lon ? Number(lon).toFixed(6) : null });
            onSaved(updated); setEditing(false); setSaved(true);
        } catch (err) { setError(errorText(err)); } finally { setBusy(false); }
    };
    return <form onSubmit={save} className="flex w-full flex-col gap-4">
        <fieldset disabled={busy} className="flex flex-col gap-4">
            <FormField label="Имя" htmlFor="profile-name"><Input id="profile-name" required maxLength={120} value={form.display_name} onChange={(display_name) => setForm({ ...form, display_name })} /></FormField>
            <FormField label="Никнейм" htmlFor="profile-username"><Input id="profile-username" required maxLength={50} value={form.username} onChange={(username) => setForm({ ...form, username })} /></FormField>
            <FormField label="О себе" htmlFor="profile-bio"><Textarea id="profile-bio" maxLength={2000} value={form.bio} onChange={(bio) => setForm({ ...form, bio })} /></FormField>
            <FormField label="Город" htmlFor="profile-city"><Input id="profile-city" maxLength={120} value={form.city} onChange={(city) => setForm({ ...form, city })} /></FormField>
            <FormField label="Широта" htmlFor="profile-lat"><Input id="profile-lat" inputMode="decimal" value={form.latitude} onChange={(latitude) => setForm({ ...form, latitude })} /></FormField>
            <FormField label="Долгота" htmlFor="profile-lon" hint="Оставьте обе координаты пустыми, чтобы удалить их."><Input id="profile-lon" inputMode="decimal" value={form.longitude} onChange={(longitude) => setForm({ ...form, longitude })} /></FormField>
            {error && <Notice tone="error">{error}</Notice>}
            <div className="flex gap-2"><Button type="submit">{busy ? "Сохраняем…" : "Сохранить профиль"}</Button><Button onClick={() => setEditing(false)}>Отмена</Button></div>
        </fieldset>
    </form>;
};
