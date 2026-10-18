import type { ReactNode } from "react";

export type NoticeTone = "info" | "error" | "success";

const toneClassMap: Record<NoticeTone, string> = {
    info: "border-bordersoft bg-surface-muted text-textsecondary",
    error: "border-bordererror/40 bg-error/8 text-texterror",
    success: "border-bordersuccess/40 bg-success/8 text-textsuccess",
};

interface NoticeProps {
    tone?: NoticeTone;
    children: ReactNode;
    className?: string;
}

export const Notice = ({ tone = "info", children, className = "" }: NoticeProps) => (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-xl border px-4 py-3 text-body ${toneClassMap[tone]} ${className}`}>
        {children}
    </div>
);

export const Loader = ({ text = "Загружаем…" }: { text?: string }) => (
    <div className="flex w-full items-center justify-center gap-3 py-10 text-body text-textmuted" role="status">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-textmuted/30 border-t-borderlight" />
        {text}
    </div>
);
