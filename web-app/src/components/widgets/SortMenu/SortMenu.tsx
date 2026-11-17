import { useEffect, useRef, useState } from "react";
import type { EventSort } from "../../../models";

const SORT_LABELS: Record<EventSort, string> = {
    relevance: "Рекомендуем",
    novelty: "Сначала новые",
    title: "По названию",
    distance: "Рядом со мной",
};

const SORTS = Object.keys(SORT_LABELS) as EventSort[];

interface SortMenuProps {
    value: EventSort;
    onChange: (sort: EventSort) => void;
}

/** Квадратная кнопка рядом с поиском и выпадающий список сортировок ленты. */
export const SortMenu = ({ value, onChange }: SortMenuProps) => {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!open) return;
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
    }, [open]);

    const choose = (sort: EventSort) => {
        setOpen(false);
        if (sort !== value) onChange(sort);
    };

    return (
        <div ref={rootRef} className="relative shrink-0">
            <button
                type="button"
                onClick={() => setOpen((previous) => !previous)}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-label={`Сортировка: ${SORT_LABELS[value]}`}
                title={`Сортировка: ${SORT_LABELS[value]}`}
                className="inline-flex h-[41px] w-[41px] cursor-pointer items-center justify-center rounded-lg bg-primary transition-all hover:bg-borderlight"
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

            {open && (
                <ul
                    role="menu"
                    aria-label="Сортировка ленты"
                    className="absolute right-0 top-full z-20 mt-1 flex min-w-[190px] flex-col gap-1 rounded-lg border border-bordermain bg-primary p-1 shadow-hover"
                >
                    {SORTS.map((sort) => (
                        <li key={sort} role="none">
                            <button
                                type="button"
                                role="menuitemradio"
                                aria-checked={sort === value}
                                onClick={() => choose(sort)}
                                className={`flex w-full cursor-pointer items-center justify-between gap-3 rounded-md px-3 py-2 text-left text-textprimary transition hover:bg-cards-surface ${
                                    sort === value ? "bg-cards-surface font-medium" : ""
                                }`}
                            >
                                {SORT_LABELS[sort]}
                                {sort === value && <span aria-hidden="true">✓</span>}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
};
