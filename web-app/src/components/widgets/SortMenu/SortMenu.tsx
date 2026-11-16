import { useEffect, useRef, useState } from "react";
import type { FeedRanking } from "../../../models";

const RANKING_LABELS: Record<FeedRanking, string> = {
    relevance: "Рекомендуем",
    novelty: "Сначала новые",
    title: "По названию",
    distance: "Рядом со мной",
};

const RANKINGS = Object.keys(RANKING_LABELS) as FeedRanking[];

interface SortMenuProps {
    value: FeedRanking;
    onChange: (ranking: FeedRanking) => void;
    /** Причина, по которой сортировка недоступна; кнопка тогда неактивна. */
    disabledReason?: string;
}

/** Квадратная кнопка рядом с поиском и выпадающий список сортировок ленты. */
export const SortMenu = ({ value, onChange, disabledReason }: SortMenuProps) => {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);
    const disabled = Boolean(disabledReason);
    const isOpen = open && !disabled;

    useEffect(() => {
        if (!isOpen) return;
        const closeOnOutsideClick = (event: MouseEvent) => {
            if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
        };
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape") setOpen(false);
        };
        document.addEventListener("mousedown", closeOnOutsideClick);
        document.addEventListener("keydown", closeOnEscape);
        return () => {
            document.removeEventListener("mousedown", closeOnOutsideClick);
            document.removeEventListener("keydown", closeOnEscape);
        };
    }, [isOpen]);

    const choose = (ranking: FeedRanking) => {
        setOpen(false);
        if (ranking !== value) onChange(ranking);
    };

    return (
        <div ref={rootRef} className="relative shrink-0">
            <button
                type="button"
                onClick={() => setOpen((previous) => !previous)}
                disabled={disabled}
                aria-haspopup="menu"
                aria-expanded={isOpen}
                aria-label={`Сортировка: ${RANKING_LABELS[value]}`}
                title={disabledReason ?? `Сортировка: ${RANKING_LABELS[value]}`}
                className="inline-flex h-[41px] w-[41px] cursor-pointer items-center justify-center rounded-lg bg-primary transition-all hover:bg-borderlight disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-primary"
            >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path
                        d="M7 4V20M7 20L3 16M7 20L11 16M17 20V4M17 4L13 8M17 4L21 8"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    />
                </svg>
            </button>

            {isOpen && (
                <ul
                    role="menu"
                    aria-label="Сортировка ленты"
                    className="absolute right-0 top-full z-20 mt-1 flex min-w-[190px] flex-col gap-1 rounded-lg border border-bordermain bg-primary p-1 shadow-hover"
                >
                    {RANKINGS.map((ranking) => (
                        <li key={ranking} role="none">
                            <button
                                type="button"
                                role="menuitemradio"
                                aria-checked={ranking === value}
                                onClick={() => choose(ranking)}
                                className={`flex w-full cursor-pointer items-center justify-between gap-3 rounded-md px-3 py-2 text-left text-textprimary transition hover:bg-cards-surface ${
                                    ranking === value ? "bg-cards-surface font-medium" : ""
                                }`}
                            >
                                {RANKING_LABELS[ranking]}
                                {ranking === value && <span aria-hidden="true">✓</span>}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
};
