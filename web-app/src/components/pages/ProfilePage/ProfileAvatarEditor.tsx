import { useState } from "react";
import { errorText } from "../../../api";
import { createAvatarSaver } from "../../../api/profileImage";
import type { Profile } from "../../../models";
import type { ImageChange } from "../../../utils/media";
import { Button, ImagePicker, Notice } from "../../ui";

interface ProfileAvatarEditorProps {
    profile: Profile;
    onSaved: (profile: Profile) => void;
}

export const ProfileAvatarEditor = ({ profile, onSaved }: ProfileAvatarEditorProps) => {
    const [save] = useState(() => createAvatarSaver(profile.id));
    const [selection, setSelection] = useState<ImageChange>({ kind: "keep" });
    const [error, setError] = useState<string | null>(null);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<string | null>(null);

    const submit = async (event: React.FormEvent) => {
        event.preventDefault();
        if (busy || error || selection.kind === "keep") return;
        setBusy(true);
        setMessage(null);
        setSaveError(null);
        try {
            const updated = await save(selection);
            onSaved(updated);
            setSelection({ kind: "keep" });
            setMessage(selection.kind === "remove" ? "Фотография удалена." : "Фотография профиля обновлена.");
        } catch (failure) {
            setSaveError(errorText(failure));
        } finally {
            setBusy(false);
        }
    };

    return (
        <form onSubmit={submit} className="flex w-full flex-col gap-3 rounded-lg border-2 border-borderlight p-4">
            <ImagePicker
                id="profile-avatar"
                label="Фотография профиля"
                value={selection}
                initialUrl={profile.avatar_url}
                viewerId={profile.id}
                disabled={busy}
                error={error}
                removeLabel="Убрать фотографию"
                removedHint="Фотография будет удалена из профиля после сохранения."
                emptyHint="Фото будет видно другим пользователям."
                previewClassName="h-40 w-40 object-cover"
                onChange={(value) => {
                    setSelection(value);
                    setMessage(null);
                    setSaveError(null);
                }}
                onError={setError}
            />
            <div className="flex flex-wrap gap-2">
                <Button type="submit" state="fixed1" disabled={busy || Boolean(error) || selection.kind === "keep"}>
                    {busy ? "Сохраняем…" : "Сохранить фотографию"}
                </Button>
                {(selection.kind !== "keep" || error) && (
                    <Button disabled={busy} onClick={() => {
                        setSelection({ kind: "keep" });
                        setError(null);
                        setMessage(null);
                        setSaveError(null);
                    }}>
                        Отмена
                    </Button>
                )}
            </div>
            {message && <Notice tone="success">{message}</Notice>}
            {saveError && <Notice tone="error">{saveError} Повторите сохранение.</Notice>}
        </form>
    );
};
