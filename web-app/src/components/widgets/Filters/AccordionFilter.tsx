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
        <div className="flex flex-col gap-[5px]">
            <div
                className="flex h-[30px] cursor-pointer items-center justify-between rounded-lg border border-secondary bg-primary px-4 transition hover:bg-primary/90"
                onClick={() => setIsOpen((prev) => !prev)}
                role="button"
                aria-expanded={isOpen}
            >
                <div className="font-medium text-textprimary">
                    {title}
                    {activeCount > 0 && <span className="ml-2 text-small text-textsecondary">({activeCount})</span>}
                </div>
                <div className={`transition-transform ${isOpen ? "rotate-90" : ""}`}>▶</div>
            </div>

            <div
                className={`overflow-hidden transition-all duration-300 ${
                    isOpen ? "max-h-[500px] opacity-100" : "max-h-0 opacity-0"
                }`}
            >
                <div className="flex flex-col gap-2.5 rounded-lg bg-cards-surface p-2.5">{children}</div>
            </div>
        </div>
    );
};
