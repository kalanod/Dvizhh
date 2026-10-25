import type { ReactNode } from "react";
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import {
    errorText,
    getUser,
    listFriendRequests,
    listFriends,
    mediaSrc,
    removeFriend,
    requestFriendship,
    respondToFriendship,
    setAvatar,
    updateProfile,
    uploadMedia,
} from "../../../api";
import { notifyInboxChanged, useAsync, useCurrentUser } from "../../../hooks";
import type { Profile, UpdateProfileInput } from "../../../models";
import { MainLayout } from "../../layouts";
import { Avatar, Button, FileButton, FormField, Input, Loader, Notice, Textarea } from "../../ui";
import { PeopleList } from "../../widgets";
import { formatJoinedAt } from "../../../utils/format";

/** /profile — свой профиль, /users/:id — профиль другого пользователя. */
export const ProfilePage = () => {
    const { id } = useParams();
    const { userId, loading } = useCurrentUser();
    const profileId = id ?? userId;

    if (!id && loading) {
        return (
            <MainLayout>
                <Loader />
            </MainLayout>
        );
    }

    if (!profileId) {
        return <Navigate to="/login?next=/profile" replace />;
    }

    return (
        <MainLayout>
            <ProfileDetailsSection key={profileId} profileId={profileId} />
        </MainLayout>
    );
};

const Field = ({ label, children }: { label: string; children: ReactNode }) => (
    <div className="flex flex-col gap-2">
        <label className="text-buttons text-textsecondary">{label}</label>
        <div className="text-body break-words whitespace-pre-line text-textprimary">{children}</div>
    </div>
);

const ProfileDetailsSection = ({ profileId }: { profileId: string }) => {
    const { userId, user: me } = useCurrentUser();
    const isMe = profileId === userId;
    const profileState = useAsync((signal) => (isMe && me ? Promise.resolve(me) : getUser(profileId, signal)), profileId);
    const friendsState = useAsync((signal) => listFriends(profileId, signal), profileId);
    const [editing, setEditing] = useState(false);
    // Свой профиль берём из контекста: он обновляется сразу после редактирования.
    const profile = isMe && me ? me : profileState.data;

    return (
        <div className="flex flex-col gap-5">
            <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
                {profileState.loading && !profile ? (
                    <Loader />
                ) : !profile ? (
                    <div className="flex w-full items-center justify-center p-8">
                        <p className="text-h2 text-textprimary">{errorText(profileState.error)}</p>
                    </div>
                ) : (
                    <div className="flex w-full flex-col items-start gap-[10px] rounded-lg bg-cards-surface p-4 sm:p-8">
                        <div className="mb-4 flex w-full flex-wrap items-center justify-between gap-2">
                            <h2 className="text-h2 text-textprimary">{isMe ? "Профиль" : "Профиль пользователя"}</h2>
                            {isMe && !editing && (
                                <Button state="fixed2" className="!h-[30px] !px-4" onClick={() => setEditing(true)}>
                                    Редактировать
                                </Button>
                            )}
                            {!isMe && userId && <FriendshipActions me={userId} other={profile} onChanged={friendsState.reload} />}
                        </div>

                        {isMe && editing ? (
                            <ProfileEditForm profile={profile} onDone={() => setEditing(false)} />
                        ) : (
                            <div className="flex w-full flex-wrap gap-6 sm:gap-8">
                                <div className="flex flex-col items-start gap-2">
                                    <Avatar name={profile.display_name} src={mediaSrc(profile.avatar_url, userId)} size="lg" />
                                    {isMe && <AvatarActions profile={profile} />}
                                </div>
                                <div className="flex min-w-0 flex-1 flex-col gap-6">
                                    <Field label="Имя">{profile.display_name}</Field>
                                    <Field label="Никнейм">@{profile.username}</Field>
                                    {profile.city && <Field label="Город">{profile.city}</Field>}
                                    {profile.bio && <Field label="О себе">{profile.bio}</Field>}
                                    <Field label="На Движже">с {formatJoinedAt(profile.created_at)}</Field>
                                    {isMe && <ProfileIdField profile={profile} />}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                <div className="flex w-full flex-col gap-[10px] rounded-lg bg-cards-surface p-4 sm:p-8">
                    <h2 className="text-h2 text-textprimary">
                        Друзья{friendsState.data && friendsState.data.length > 0 ? ` (${friendsState.data.length})` : ""}
                    </h2>
                    {friendsState.loading ? (
                        <span className="text-body text-textsecondary">Загрузка...</span>
                    ) : friendsState.error !== undefined ? (
                        <Notice tone="error">{errorText(friendsState.error)}</Notice>
                    ) : (
                        <PeopleList
                            emptyText={isMe ? "Добавляйте друзей со страниц их профилей." : "Пока без друзей."}
                            people={(friendsState.data ?? []).map((friend) => ({ user: friend, avatarUrl: friend.avatar_url }))}
                        />
                    )}
                </div>
            </section>
        </div>
    );
};

/** Пустая строка в необязательном поле очищает его (null), как и ожидает PATCH. */
const optional = (value: string) => value.trim() || null;

const ProfileEditForm = ({ profile, onDone }: { profile: Profile; onDone: () => void }) => {
    const { signIn } = useCurrentUser();
    const [displayName, setDisplayName] = useState(profile.display_name);
    const [username, setUsername] = useState(profile.username);
    const [city, setCity] = useState(profile.city ?? "");
    const [bio, setBio] = useState(profile.bio ?? "");
    const [error, setError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        // Отправляем только изменённые поля: пустой PATCH backend отклоняет.
        const patch: UpdateProfileInput = {};
        if (displayName.trim() !== profile.display_name) patch.display_name = displayName.trim();
        if (username.trim() !== profile.username) patch.username = username.trim();
        if (optional(city) !== profile.city) patch.city = optional(city);
        if (optional(bio) !== profile.bio) patch.bio = optional(bio);

        if (Object.keys(patch).length === 0) {
            onDone();
            return;
        }
        if (patch.display_name === "") {
            setError("Укажите имя.");
            return;
        }
        if (patch.username !== undefined && !/^[a-z0-9_]{3,50}$/.test(patch.username)) {
            setError("Никнейм: 3–50 символов — строчные латинские буквы, цифры и «_».");
            return;
        }

        setSaving(true);
        setError(null);
        try {
            signIn(await updateProfile(profile.id, patch));
            onDone();
        } catch (err) {
            setError(errorText(err));
            setSaving(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} noValidate className="flex w-full flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
                <FormField label="Имя" htmlFor="display-name" required>
                    <Input id="display-name" maxLength={120} value={displayName} onChange={setDisplayName} />
                </FormField>
                <FormField label="Никнейм" htmlFor="username" required hint="Строчные латинские буквы, цифры и «_»">
                    <Input id="username" maxLength={50} value={username} onChange={(value) => setUsername(value.toLowerCase())} />
                </FormField>
            </div>
            <FormField label="Город" htmlFor="city">
                <Input id="city" maxLength={120} placeholder="Санкт-Петербург" value={city} onChange={setCity} />
            </FormField>
            <FormField label="О себе" htmlFor="bio">
                <Textarea id="bio" rows={4} maxLength={2000} value={bio} onChange={setBio} />
            </FormField>
            {error && <Notice tone="error">{error}</Notice>}
            <div className="flex flex-wrap justify-end gap-2">
                <Button state="hover1" onClick={onDone}>
                    Отмена
                </Button>
                <Button type="submit" state="fixed1" disabled={saving}>
                    {saving ? "Сохраняем…" : "Сохранить"}
                </Button>
            </div>
        </form>
    );
};

const AvatarActions = ({ profile }: { profile: Profile }) => {
    const { signIn } = useCurrentUser();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const run = async (action: () => Promise<Profile>) => {
        setBusy(true);
        setError(null);
        try {
            signIn(await action());
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="flex max-w-[180px] flex-col gap-1.5">
            <FileButton
                state="hover1"
                className="!h-[30px] !px-3"
                disabled={busy}
                onFile={(file) => run(async () => setAvatar(profile.id, (await uploadMedia(profile.id, file)).id))}
            >
                {busy ? "Загружаем…" : profile.avatar_media_id ? "Сменить фото" : "Загрузить фото"}
            </FileButton>
            {profile.avatar_media_id && !busy && (
                <Button state="hover1" className="!h-[30px] !px-3" onClick={() => run(() => setAvatar(profile.id, null))}>
                    Убрать фото
                </Button>
            )}
            {error && <span className="text-small text-texterror">{error}</span>}
        </div>
    );
};

const ProfileIdField = ({ profile }: { profile: Profile }) => {
    const [copied, setCopied] = useState(false);

    const copy = async () => {
        try {
            await navigator.clipboard.writeText(profile.id);
            setCopied(true);
        } catch {
            setCopied(false);
        }
    };

    return (
        <div className="flex flex-col gap-2">
            <label className="text-buttons text-textsecondary">ID профиля (нужен для входа)</label>
            <div className="flex flex-wrap items-center gap-2">
                <code className="min-w-0 rounded-lg border-2 border-secondary bg-primary px-4 py-2 font-mono text-[13px] break-all text-textprimary">
                    {profile.id}
                </code>
                <Button state="fixed2" className="!h-[30px] !px-4" onClick={copy}>
                    {copied ? "Скопировано" : "Копировать"}
                </Button>
            </div>
        </div>
    );
};

interface FriendshipActionsProps {
    me: string;
    other: Profile;
    onChanged: () => void;
}

type Relation = "friend" | "incoming" | "outgoing" | "none";

const loadRelation = async (me: string, otherId: string, signal: AbortSignal): Promise<Relation> => {
    const [friends, incoming, outgoing] = await Promise.all([
        listFriends(me, signal),
        listFriendRequests(me, "incoming", { limit: 100, signal }),
        listFriendRequests(me, "outgoing", { limit: 100, signal }),
    ]);
    if (friends.some((friend) => friend.id === otherId)) return "friend";
    if (incoming.some((request) => request.user.id === otherId)) return "incoming";
    if (outgoing.some((request) => request.user.id === otherId)) return "outgoing";
    return "none";
};

const FriendshipActions = ({ me, other, onChanged }: FriendshipActionsProps) => {
    const relationState = useAsync((signal) => loadRelation(me, other.id, signal), `${me}:${other.id}`);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const run = async (action: () => Promise<unknown>, success: string) => {
        setBusy(true);
        setError(null);
        setMessage(null);
        try {
            await action();
            setMessage(success);
            relationState.reload();
            onChanged();
            notifyInboxChanged();
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    };

    if (relationState.loading) return null;

    const small = "!h-[30px] !px-4";

    return (
        <div className="flex flex-col items-start gap-2 sm:items-end">
            <div className="flex flex-wrap gap-2">
                {relationState.data === "friend" && (
                    <Button state="hover1" className={small} disabled={busy} onClick={() => run(() => removeFriend(me, other.id), "Пользователь удалён из друзей.")}>
                        Удалить из друзей
                    </Button>
                )}
                {relationState.data === "incoming" && (
                    <>
                        <span className="self-center text-small text-textsecondary">Хочет добавить вас в друзья</span>
                        <Button state="fixed2" className={small} disabled={busy} onClick={() => run(() => respondToFriendship(me, other.id, true), "Теперь вы друзья!")}>
                            Принять
                        </Button>
                        <Button state="hover1" className={small} disabled={busy} onClick={() => run(() => respondToFriendship(me, other.id, false), "Заявка отклонена.")}>
                            Отклонить
                        </Button>
                    </>
                )}
                {relationState.data === "outgoing" && (
                    <Button state="disabled" className={small}>
                        Заявка отправлена
                    </Button>
                )}
                {(relationState.data === "none" || relationState.data === undefined) && (
                    <Button state="fixed2" className={small} disabled={busy} onClick={() => run(() => requestFriendship(me, other.id), "Заявка в друзья отправлена.")}>
                        Добавить в друзья
                    </Button>
                )}
            </div>
            {message && !error && <span className="text-small text-textsuccess">{message}</span>}
            {error && <span className="text-small text-texterror">{error}</span>}
            {relationState.error !== undefined && !error && <span className="text-small text-texterror">{errorText(relationState.error)}</span>}
        </div>
    );
};
