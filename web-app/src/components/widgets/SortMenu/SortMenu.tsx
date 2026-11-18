import { useCallback, useEffect, useRef, useState } from "react";
import type { EventSort } from "../../../models";

const SORT_LABELS: Record<EventSort, string> = {
    relevance: "Рекомендуем",
    novelty: "По новизне",
    title: "По названию",
    distance: "Рядом со мной",
    start: "По дате начала",
};

const SORTS = Object.keys(SORT_LABELS) as EventSort[];

interface SortMenuProps {
    value: EventSort;
    onChange: (sort: EventSort) => void;
    allowDistance?: boolean;
}

/** Квадратная кнопка рядом с поиском и выпадающий список сортировок ленты. */
export const SortMenu = ({ value, onChange, allowDistance = true }: SortMenuProps) => {
    const [open, setOpen] = useState(false);
    const [placement, setPlacement] = useState<{ above: boolean; maxHeight?: number }>({ above: false });
    const rootRef = useRef<HTMLDivElement>(null);
    const labels = SORT_LABELS;

    const updatePlacement = useCallback(() => {
        const bounds = rootRef.current?.getBoundingClientRect();
        if (!bounds) return;
        const viewport = window.visualViewport;
        const top = viewport?.offsetTop ?? 0;
        const bottom = top + (viewport?.height ?? window.innerHeight);
        const above = Math.max(0, bounds.top - top);
        const below = Math.max(0, bottom - bounds.bottom);
        setPlacement({ above: above > below, maxHeight: Math.max(0, Math.max(above, below) - 8) });
    }, []);

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
        window.addEventListener("resize", updatePlacement);
        window.addEventListener("scroll", updatePlacement, { capture: true, passive: true });
        window.visualViewport?.addEventListener("resize", updatePlacement);
        window.visualViewport?.addEventListener("scroll", updatePlacement);
        return () => {
            document.removeEventListener("mousedown", closeOnOutsideClick);
            document.removeEventListener("keydown", closeOnEscape);
            window.removeEventListener("resize", updatePlacement);
            window.removeEventListener("scroll", updatePlacement, true);
            window.visualViewport?.removeEventListener("resize", updatePlacement);
            window.visualViewport?.removeEventListener("scroll", updatePlacement);
        };
    }, [open, updatePlacement]);

    const choose = (sort: EventSort) => {
        setOpen(false);
        onChange(sort);
    };

    return (
        <div ref={rootRef} className="relative shrink-0">
            <button
                type="button"
                onClick={() => {
                    if (!open) updatePlacement();
                    setOpen((previous) => !previous);
                }}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-label={`Сортировка: ${labels[value]}`}
                title={`Сортировка: ${labels[value]}`}
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
                    style={{ maxHeight: placement.maxHeight }}
                    className={`absolute right-0 z-20 flex min-w-[190px] flex-col gap-1 overflow-y-auto rounded-lg border border-bordermain bg-primary p-1 shadow-hover ${placement.above ? "bottom-full mb-1" : "top-full mt-1"}`}
                >
                    {SORTS.filter((sort) => allowDistance || sort !== "distance").map((sort) => (
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
                                {labels[sort]}
                                {sort === value && <span aria-hidden="true">✓</span>}
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
};
