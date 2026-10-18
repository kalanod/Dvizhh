import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar } from "../../ui";
import type { UserSummary } from "../../../models";

export interface PersonRow {
    user: UserSummary;
    note?: ReactNode;
    actions?: ReactNode;
}

interface PeopleListProps {
    people: PersonRow[];
    emptyText: string;
}

/** Список людей: участники события, друзья. */
export const PeopleList = ({ people, emptyText }: PeopleListProps) => {
    const navigate = useNavigate();

    if (people.length === 0) {
        return <p className="px-1 text-body text-textsecondary">{emptyText}</p>;
    }

    return (
        <ul className="flex flex-col gap-1.5">
            {people.map(({ user, note, actions }) => (
                <li key={user.id} className="flex items-center gap-3 rounded-xl px-2 py-1.5 transition-colors hover:bg-surface-muted">
                    <button
                        type="button"
                        onClick={() => navigate(`/users/${user.id}`)}
                        className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left"
                    >
                        <Avatar name={user.display_name} seed={user.id} />
                        <span className="flex min-w-0 flex-col">
                            <span className="truncate text-body font-bold text-textprimary">{user.display_name}</span>
                            <span className="truncate text-small font-medium text-textsecondary">
                                @{user.username}
                                {note && <> · {note}</>}
                            </span>
                        </span>
                    </button>
                    {actions && <div className="flex shrink-0 gap-1.5">{actions}</div>}
                </li>
            ))}
        </ul>
    );
};
