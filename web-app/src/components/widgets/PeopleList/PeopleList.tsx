import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "../../ui";
import type { UserSummary } from "../../../models";

export interface PersonRow {
    user: UserSummary;
    /** avatar_url профиля, если он известен (в UserSummary его нет). */
    avatarUrl?: string | null;
    note?: ReactNode;
    actions?: ReactNode;
}

interface PeopleListProps {
    people: PersonRow[];
    emptyText: string;
}

/** Список людей (участники, друзья): строки в стиле NotificationFrame шаблона. */
export const PeopleList = ({ people, emptyText }: PeopleListProps) => {
    const navigate = useNavigate();

    if (people.length === 0) {
        return <p className="text-body text-textsecondary">{emptyText}</p>;
    }

    return (
        <div className="flex w-full flex-col gap-[10px]">
            {people.map(({ user, avatarUrl, note, actions }) => (
                <div
                    key={user.id}
                    className="flex min-h-[42px] w-full items-center gap-2.5 overflow-hidden rounded-lg bg-primary p-2.5 transition-colors hover:bg-primary/80"
                >
                    <div className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5" onClick={() => navigate(`/users/${user.id}`)}>
                        <Avatar name={user.display_name} src={avatarUrl} size="sm" />
                        <span className="truncate text-body text-black">{user.display_name}</span>
                        <span className="truncate text-duration text-textsecondary">
                            @{user.username}
                            {note && <> · {note}</>}
                        </span>
                    </div>
                    {actions && <div className="flex shrink-0 gap-1.5">{actions}</div>}
                </div>
            ))}
        </div>
    );
};
