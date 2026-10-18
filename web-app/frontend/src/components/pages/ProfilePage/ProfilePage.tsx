import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { errorText, getUser, listFriends, removeFriend, requestFriendship, respondToFriendship } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import type { Profile } from "../../../models";
import { MainLayout } from "../../layouts";
import { Avatar, Button, Loader, Notice } from "../../ui";
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
            <ProfileView key={profileId} profileId={profileId} />
        </MainLayout>
    );
};

const ProfileView = ({ profileId }: { profileId: string }) => {
    const { userId, user: me } = useCurrentUser();
    const isMe = profileId === userId;
    const profileState = useAsync(() => (isMe && me ? Promise.resolve(me) : getUser(profileId)), profileId);
    const friendsState = useAsync(() => listFriends(profileId), profileId);
    const profile = profileState.data;

    if (profileState.loading) return <Loader />;
    if (!profile) return <Notice tone="error">{errorText(profileState.error)}</Notice>;

    return (
        <div className="flex w-full flex-col gap-[12px] lg:flex-row lg:items-start">
            <section className="flex min-w-0 flex-1 flex-col gap-5 rounded-2xl bg-cards-surface p-6 shadow-card sm:p-8">
                <div className="flex flex-wrap items-center gap-5">
                    <Avatar name={profile.display_name} seed={profile.id} size="lg" />
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <h1 className="text-h1 break-words text-textprimary">{profile.display_name}</h1>
                        <span className="text-body text-textsecondary">
                            @{profile.username}
                            {profile.city && <> · 📍 {profile.city}</>}
                        </span>
                        <span className="text-small font-medium text-textsecondary">На Движже с {formatJoinedAt(profile.created_at)}</span>
                    </div>
                </div>

                {profile.bio && <p className="text-body whitespace-pre-line text-textprimary/85">{profile.bio}</p>}

                {isMe ? (
                    <ProfileIdBox profile={profile} />
                ) : (
                    userId && <FriendshipActions me={userId} other={profile} onChanged={friendsState.reload} />
                )}
            </section>

            <aside className="flex h-fit w-full flex-col gap-2 rounded-2xl bg-cards-surface p-5 shadow-card lg:w-[340px] lg:shrink-0">
                <h2 className="text-h3 text-textprimary">
                    Друзья{friendsState.data && friendsState.data.length > 0 ? ` (${friendsState.data.length})` : ""}
                </h2>
                {friendsState.loading ? (
                    <span className="text-small text-textsecondary">Загружаем…</span>
                ) : friendsState.error !== undefined ? (
                    <Notice tone="error">{errorText(friendsState.error)}</Notice>
                ) : (
                    <PeopleList
                        emptyText={isMe ? "Добавляйте друзей со страниц их профилей." : "Пока без друзей."}
                        people={(friendsState.data ?? []).map((friend) => ({ user: friend }))}
                    />
                )}
            </aside>
        </div>
    );
};

const ProfileIdBox = ({ profile }: { profile: Profile }) => {
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
        <div className="flex flex-col gap-2 rounded-xl bg-surface-muted p-4">
            <span className="text-small text-textsecondary">ID профиля — нужен для входа, пока нет авторизации</span>
            <div className="flex flex-wrap items-center gap-2">
                <code className="min-w-0 flex-1 rounded-lg bg-primary px-3 py-2 font-mono text-[13px] break-all text-textprimary">
                    {profile.id}
                </code>
                <Button state="hover2" onClick={copy}>
                    {copied ? "Скопировано ✓" : "Копировать"}
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

const FriendshipActions = ({ me, other, onChanged }: FriendshipActionsProps) => {
    const myFriends = useAsync(() => listFriends(me), me);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const isFriend = myFriends.data?.some((friend) => friend.id === other.id) ?? false;

    const run = async (action: () => Promise<unknown>, success: string) => {
        setBusy(true);
        setError(null);
        setMessage(null);
        try {
            await action();
            setMessage(success);
            myFriends.reload();
            onChanged();
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    };

    if (myFriends.loading) return null;

    return (
        <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
                {isFriend ? (
                    <Button
                        state="outline"
                        disabled={busy}
                        onClick={() => run(() => removeFriend(me, other.id), "Пользователь удалён из друзей.")}
                    >
                        Удалить из друзей
                    </Button>
                ) : (
                    <>
                        <Button
                            state="hover1"
                            disabled={busy}
                            onClick={() => run(() => requestFriendship(me, other.id), "Заявка в друзья отправлена.")}
                        >
                            Добавить в друзья
                        </Button>
                        <Button
                            state="hover2"
                            disabled={busy}
                            title="Если этот пользователь уже отправил вам заявку"
                            onClick={() => run(() => respondToFriendship(me, other.id, true), "Теперь вы друзья!")}
                        >
                            Принять заявку
                        </Button>
                    </>
                )}
            </div>
            {message && !error && <span className="text-small text-textsuccess">{message}</span>}
            {error && <Notice tone="error">{error}</Notice>}
        </div>
    );
};
