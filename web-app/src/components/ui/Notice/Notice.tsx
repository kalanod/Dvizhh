import type { ReactNode } from "react";

export type NoticeTone = "info" | "error" | "success";

const toneClassMap: Record<NoticeTone, string> = {
    info: "border-borderlight bg-cards-surface text-textprimary",
    error: "border-bordererror bg-cards-surface text-texterror",
    success: "border-bordersuccess bg-cards-surface text-textsuccess",
};

interface NoticeProps {
    tone?: NoticeTone;
    children: ReactNode;
    className?: string;
}

export const Notice = ({ tone = "info", children, className = "" }: NoticeProps) => (
    <div role={tone === "error" ? "alert" : "status"} className={`w-full rounded-lg border-2 px-4 py-2 text-body ${toneClassMap[tone]} ${className}`}>
        {children}
    </div>
);

export const Loader = ({ text = "Загрузка..." }: { text?: string }) => (
    <div className="flex w-full items-center justify-center gap-3 p-8" role="status">
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-borderlight border-t-bordermain" />
        <span className="text-h3 text-textprimary">{text}</span>
    </div>
);
