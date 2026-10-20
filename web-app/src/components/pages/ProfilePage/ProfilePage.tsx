import type { ReactNode } from "react";
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
    const profileState = useAsync(() => (isMe && me ? Promise.resolve(me) : getUser(profileId)), profileId);
    const friendsState = useAsync(() => listFriends(profileId), profileId);
    const profile = profileState.data;

    return (
        <div className="flex flex-col gap-5">
            <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
                {profileState.loading ? (
                    <Loader />
                ) : !profile ? (
                    <div className="flex w-full items-center justify-center p-8">
                        <p className="text-h2 text-textprimary">{errorText(profileState.error)}</p>
                    </div>
                ) : (
                    <div className="flex w-full flex-col items-start gap-[10px] rounded-lg bg-cards-surface p-8">
                        <div className="mb-4 flex w-full flex-wrap items-center justify-between gap-2">
                            <h2 className="text-h2 text-textprimary">{isMe ? "Профиль" : "Профиль пользователя"}</h2>
                            {!isMe && userId && <FriendshipActions me={userId} other={profile} onChanged={friendsState.reload} />}
                        </div>

                        <div className="flex w-full flex-wrap gap-8">
                            <Avatar name={profile.display_name} size="lg" />
                            <div className="flex min-w-0 flex-1 flex-col gap-6">
                                <Field label="Имя">{profile.display_name}</Field>
                                <Field label="Никнейм">@{profile.username}</Field>
                                {profile.city && <Field label="Город">{profile.city}</Field>}
                                {profile.bio && <Field label="О себе">{profile.bio}</Field>}
                                <Field label="На Движже">с {formatJoinedAt(profile.created_at)}</Field>
                                {isMe && <ProfileIdField profile={profile} />}
                            </div>
                        </div>
                    </div>
                )}

                <div className="flex w-full flex-col gap-[10px] rounded-lg bg-cards-surface p-8">
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
                            people={(friendsState.data ?? []).map((friend) => ({ user: friend }))}
                        />
                    )}
                </div>
            </section>
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
        <div className="flex flex-col items-end gap-2">
            <div className="flex flex-wrap gap-2">
                {isFriend ? (
                    <Button
                        state="hover1"
                        className="!h-[30px] !px-4"
                        disabled={busy}
                        onClick={() => run(() => removeFriend(me, other.id), "Пользователь удалён из друзей.")}
                    >
                        Удалить из друзей
                    </Button>
                ) : (
                    <>
                        <Button
                            state="fixed2"
                            className="!h-[30px] !px-4"
                            disabled={busy}
                            onClick={() => run(() => requestFriendship(me, other.id), "Заявка в друзья отправлена.")}
                        >
                            Добавить в друзья
                        </Button>
                        <Button
                            state="hover1"
                            className="!h-[30px] !px-4"
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
            {error && <span className="text-small text-texterror">{error}</span>}
        </div>
    );
};
