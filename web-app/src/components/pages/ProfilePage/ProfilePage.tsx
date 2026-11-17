import type { ReactNode } from "react";
import { useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { errorText, getFriendship, getUser, listFriends, removeFriend, requestFriendship, respondToFriendship } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import type { Profile } from "../../../models";
import { MainLayout } from "../../layouts";
import { Avatar, Button, ImageViewer, Loader, Notice } from "../../ui";
import { mediaContentUrl } from "../../../utils/media";
import { PeopleList } from "../../widgets";
import { formatJoinedAt } from "../../../utils/format";
import { ProfileEditor } from "./ProfileEditor";
import { ProfileAvatarEditor } from "./ProfileAvatarEditor";
import { PasswordEditor } from "./PasswordEditor";

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
    const { userId, user: me, updateUser } = useCurrentUser();
    const isMe = profileId === userId;
    const [editing, setEditing] = useState(false);
    const profileState = useAsync(() => (isMe && me ? Promise.resolve(me) : getUser(profileId)), profileId);
    const friendsState = useAsync(() => listFriends(profileId), profileId);
    const profile = isMe && me ? me : profileState.data;

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
                    <div className="relative flex w-full flex-col items-start gap-[10px] rounded-lg bg-cards-surface p-4 sm:p-8">
                        <div className={`mb-4 flex w-full flex-wrap items-center justify-between gap-2 ${isMe ? "min-h-[41px] pr-14" : ""}`}>
                            <h2 className="text-h2 text-textprimary">{isMe ? "Профиль" : "Профиль пользователя"}</h2>
                            {!isMe && userId && <FriendshipActions me={userId} other={profile} onChanged={friendsState.reload} />}
                        </div>

                        <div className="flex w-full flex-col gap-6 sm:flex-row sm:flex-wrap sm:gap-8">
                            {isMe && me ? (
                                <ProfileAvatarEditor key={profile.id} profile={profile} editing={editing} onSaved={updateUser} />
                            ) : <ImageViewer src={mediaContentUrl(profile.avatar_url, userId)} alt={`Фото профиля ${profile.display_name}`} className="block self-start">
                                <Avatar name={profile.display_name} src={mediaContentUrl(profile.avatar_url, userId)} size="lg" />
                            </ImageViewer>}
                            <div className="flex min-w-0 flex-1 flex-col gap-6">
                                <Field label="Имя">{profile.display_name}</Field>
                                <Field label="Никнейм">@{profile.username}</Field>
                                {profile.city && <Field label="Город">{profile.city}</Field>}
                                {profile.bio && <Field label="О себе">{profile.bio}</Field>}
                                <Field label="На Движже">с {formatJoinedAt(profile.created_at)}</Field>
                            </div>
                        </div>
                        {isMe && me && <ProfileEditor profile={profile} editing={editing} onEditingChange={setEditing} onSaved={updateUser} />}
                        {isMe && me && <PasswordEditor key={`password-${profile.id}`} />}
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
                            people={(friendsState.data ?? []).map((friend) => ({ user: friend }))}
                        />
                    )}
                </div>
            </section>
        </div>
    );
};

interface FriendshipActionsProps {
    me: string;
    other: Profile;
    onChanged: () => void;
}

const FriendshipActions = ({ me, other, onChanged }: FriendshipActionsProps) => {
    const relationship = useAsync((signal) => getFriendship(me, other.id, signal), `${me}:${other.id}`);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const friendship = relationship.data;
    const action = friendship?.status === "ACCEPTED"
        ? { label: "Удалить из друзей", run: () => removeFriend(me, other.id), success: "Пользователь удалён из друзей." }
        : friendship?.status === "PENDING"
            ? friendship.requested_by_user_id === me
                ? { label: "Отменить запрос", run: () => removeFriend(me, other.id), success: "Запрос в друзья отменён." }
                : { label: "Принять заявку", run: () => respondToFriendship(me, other.id, true), success: "Теперь вы друзья!" }
            : { label: "Добавить в друзья", run: () => requestFriendship(me, other.id), success: "Заявка в друзья отправлена." };

    const run = async () => {
        setBusy(true);
        setError(null);
        setMessage(null);
        try {
            await action.run();
            setMessage(action.success);
            onChanged();
        } catch (err) {
            setError(errorText(err));
        } finally {
            relationship.reload();
            setBusy(false);
        }
    };

    return (
        <div className="flex flex-col items-start gap-2 sm:items-end">
            <Button
                state="hover1"
                className="!h-[30px] !px-4"
                disabled={busy || relationship.loading}
                onClick={relationship.error !== undefined ? relationship.reload : () => void run()}
            >
                {relationship.loading ? "Загрузка…" : relationship.error !== undefined ? "Повторить загрузку" : action.label}
            </Button>
            {message && !error && <span role="status" className="text-small text-textsuccess">{message}</span>}
            {(error || relationship.error !== undefined) && <span role="alert" className="text-small text-texterror">{error ?? errorText(relationship.error)}</span>}
        </div>
    );
};
