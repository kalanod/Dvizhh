import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { FormField } from "../../ui";

/** Focus hints live outside the scroll panel so they neither resize rows nor get clipped. */
export const SettingsField = ({ id, label, hint, required, children }: {
    id: string; label: string; hint?: string; required?: boolean; children: ReactNode;
}) => {
    const anchor = useRef<HTMLDivElement>(null);
    const tooltip = useRef<HTMLDivElement>(null);
    const [focused, setFocused] = useState(false);
    const [position, setPosition] = useState({ left: 0, top: 0 });
    useLayoutEffect(() => {
        if (!focused || !hint) return;
        const update = () => {
            if (!anchor.current || !tooltip.current) return;
            const rect = anchor.current.getBoundingClientRect();
            const width = tooltip.current.offsetWidth;
            const height = tooltip.current.offsetHeight;
            const above = rect.top - height - 8;
            setPosition({
                left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
                top: above >= 8 ? above : Math.max(8, Math.min(rect.bottom + 8, window.innerHeight - height - 8)),
            });
        };
        update();
        window.addEventListener("resize", update);
        window.addEventListener("scroll", update, true);
        return () => {
            window.removeEventListener("resize", update);
            window.removeEventListener("scroll", update, true);
        };
    }, [focused, hint]);
    return <div ref={anchor} className="w-36 min-w-32 flex-1" onFocusCapture={() => setFocused(true)} onBlurCapture={() => setFocused(false)} onKeyDown={(event) => { if (event.key === "Escape") setFocused(false); }}>
        <FormField label={label} htmlFor={id} required={required}>{children}</FormField>
        {focused && hint && createPortal(<div ref={tooltip} id={`${id}-hint`} role="tooltip" style={position} className="pointer-events-none fixed z-[100] w-80 max-w-[calc(100vw-16px)] rounded-lg border border-borderlight bg-cards-surface px-3 py-2 text-small text-textprimary shadow-lg">{hint}</div>, document.body)}
    </div>;
};
