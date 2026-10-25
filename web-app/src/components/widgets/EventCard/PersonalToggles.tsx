import { useState } from "react";
import { errorText, setDismissed, setFavorite } from "../../../api";
import { useCurrentUser } from "../../../hooks";
import type { DvizhEvent } from "../../../models";

interface PersonalTogglesProps {
    event: DvizhEvent;
    /** Обновлённая карточка из ответа backend-а. */
    onChange: (event: DvizhEvent) => void;
    className?: string;
}

const toggleClass =
    "inline-flex h-[26px] cursor-pointer items-center gap-1 rounded-lg border border-borderlight px-2 text-small transition-all hover:shadow-hover disabled:cursor-not-allowed disabled:opacity-50";

/** «В избранное» и «Не интересно» для вошедшего пользователя. */
export const PersonalToggles = ({ event, onChange, className = "" }: PersonalTogglesProps) => {
    const { userId } = useCurrentUser();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    if (!userId) return null;

    const favorite = event.personal_state?.is_favorite ?? false;
    const dismissed = event.personal_state?.is_dismissed ?? false;

    const run = async (action: () => Promise<DvizhEvent>) => {
        setBusy(true);
        setError(null);
        try {
            onChange(await action());
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    };

    return (
        // Карточка целиком кликабельна — клики по переключателям не должны открывать событие.
        <div className={`flex flex-col gap-1 ${className}`} onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-wrap gap-1.5">
                <button
                    type="button"
                    disabled={busy}
                    aria-pressed={favorite}
                    onClick={() => run(() => setFavorite(userId, event.id, !favorite))}
                    className={`${toggleClass} ${favorite ? "bg-bordermain text-textthird" : "bg-transparent text-textsecondary"}`}
                >
                    {favorite ? "★ В избранном" : "☆ В избранное"}
                </button>
                <button
                    type="button"
                    disabled={busy}
                    aria-pressed={dismissed}
                    title={dismissed ? "Снова показывать в ленте" : "Скрыть из моей ленты"}
                    onClick={() => run(() => setDismissed(userId, event.id, !dismissed))}
                    className={`${toggleClass} bg-transparent text-textsecondary`}
                >
                    {dismissed ? "↺ Вернуть в ленту" : "✕ Не интересно"}
                </button>
            </div>
            {error && <span className="text-small text-texterror">{error}</span>}
        </div>
    );
};
