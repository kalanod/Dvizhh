import type { ReactNode } from "react";
import { useState } from "react";

interface AccordionFilterProps {
    title: string;
    activeCount?: number;
    defaultOpen?: boolean;
    children: ReactNode;
}

export const AccordionFilter = ({ title, activeCount = 0, defaultOpen = false, children }: AccordionFilterProps) => {
    const [isOpen, setIsOpen] = useState(defaultOpen || activeCount > 0);

    return (
        <div className="flex flex-col gap-[6px]">
            <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setIsOpen((prev) => !prev)}
                className="flex h-[36px] cursor-pointer items-center justify-between rounded-xl bg-primary px-4 text-body font-bold text-textprimary transition hover:bg-surface-muted"
            >
                <span>
                    {title}
                    {activeCount > 0 && <span className="ml-2 text-small text-bordermain">({activeCount})</span>}
                </span>
                <span className={`text-[11px] text-textsecondary transition-transform ${isOpen ? "rotate-90" : ""}`}>▶</span>
            </button>

            <div
                className={`grid transition-all duration-300 ${isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}
            >
                <div className="overflow-hidden">
                    <div className="flex flex-col gap-2.5 rounded-xl bg-cards-surface p-2.5">{children}</div>
                </div>
            </div>
        </div>
    );
};
