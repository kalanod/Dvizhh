import { useRef, useState } from "react";
import { errorText, getMediaConfig } from "../../../api";
import { createAvatarSaver } from "../../../api/profileImage";
import { useAsync } from "../../../hooks";
import type { Profile } from "../../../models";
import { mediaContentUrl, validateCoverFile } from "../../../utils/media";
import { Avatar, Button } from "../../ui";

interface ProfileAvatarEditorProps {
    profile: Profile;
    editing: boolean;
    onSaved: (profile: Profile) => void;
}

export const ProfileAvatarEditor = ({ profile, editing, onSaved }: ProfileAvatarEditorProps) => {
    const [save] = useState(() => createAvatarSaver(profile.id));
    const config = useAsync(() => editing ? getMediaConfig() : Promise.resolve(null), `avatar-config:${editing}`);
    const input = useRef<HTMLInputElement>(null);
    const uploading = useRef(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [retryFile, setRetryFile] = useState<File | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const upload = async (file: File) => {
        if (uploading.current || !config.data) return;
        setMessage(null);
        setRetryFile(null);
        const problem = validateCoverFile(file, config.data);
        setError(problem);
        if (problem) return;
        uploading.current = true;
        setBusy(true);
        try {
            onSaved(await save({ kind: "file", file }));
            setMessage("Фотография профиля обновлена.");
        } catch (failure) {
            setError(errorText(failure));
            setRetryFile(file);
        } finally {
            uploading.current = false;
            setBusy(false);
        }
    };

    const avatar = <Avatar name={profile.display_name} src={mediaContentUrl(profile.avatar_url, profile.id)} size="lg" className="!flex" />;
    return (
        <div className="flex shrink-0 flex-col items-start gap-2">
            {editing ? (
                <>
                    <button
                        type="button"
                        aria-label={busy ? "Загрузка фотографии профиля" : "Изменить фотографию профиля"}
                        aria-busy={busy}
                        disabled={busy || !config.data}
                        title={config.data ? `JPEG, PNG или WebP, до ${config.data.max_bytes / 1024 / 1024} МБ` : "Загружаем ограничения файла…"}
                        className="group relative cursor-pointer overflow-hidden rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-borderfocus focus-visible:ring-offset-2 disabled:cursor-wait"
                        onClick={() => input.current?.click()}
                    >
                        {avatar}
                        <span aria-hidden="true" className={`absolute inset-0 flex items-center justify-center bg-white/60 text-textprimary transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100 [@media(hover:none)]:opacity-100 ${busy ? "opacity-100" : "opacity-0"}`}>
                            {busy ? <span className="h-7 w-7 animate-spin rounded-full border-2 border-current border-t-transparent" /> : (
                                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" />
                                </svg>
                            )}
                        </span>
                    </button>
                    <input
                        ref={input}
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        aria-label="Файл фотографии профиля"
                        className="hidden"
                        disabled={busy || !config.data}
                        onChange={(event) => {
                            const file = event.currentTarget.files?.[0];
                            event.currentTarget.value = "";
                            if (file) void upload(file);
                        }}
                    />
                    {config.error !== undefined && (
                        <div role="alert" className="max-w-64 text-small text-texterror">
                            Не удалось загрузить ограничения файла. <Button onClick={config.reload}>Повторить</Button>
                        </div>
                    )}
                </>
            ) : avatar}
            {busy && <span role="status" className="max-w-64 text-small text-textsecondary">Загружаем фотографию…</span>}
            {message && <span role="status" className="max-w-64 text-small text-textsuccess">{message}</span>}
            {error && <div role="alert" className="max-w-64 text-small text-texterror">{error}
                {editing && retryFile && <Button disabled={busy} onClick={() => void upload(retryFile)}>Повторить загрузку</Button>}
            </div>}
        </div>
    );
};
