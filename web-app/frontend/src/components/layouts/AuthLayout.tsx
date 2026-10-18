import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

interface AuthLayoutProps {
    title: string;
    subtitle?: string;
    children: ReactNode;
}

/** Центрированная карточка для входа и регистрации (как в LoginPage шаблона). */
export const AuthLayout = ({ title, subtitle, children }: AuthLayoutProps) => {
    const navigate = useNavigate();

    return (
        <div className="flex min-h-[calc(100svh-48px)] w-full flex-col items-center justify-center gap-6">
            <button type="button" onClick={() => navigate("/")} className="flex cursor-pointer items-center gap-3">
                <img src="/favicon.svg" alt="" className="h-[44px] w-[44px]" />
                <span className="text-logo text-textthird">
                    Движ<span className="text-borderlight">ж</span>
                </span>
            </button>
            <div className="flex w-full max-w-[460px] flex-col gap-5 rounded-3xl bg-cards-surface p-8 shadow-card sm:p-12">
                <div className="flex flex-col gap-1.5 text-center">
                    <h1 className="text-h1 text-textprimary">{title}</h1>
                    {subtitle && <p className="text-body text-textsecondary">{subtitle}</p>}
                </div>
                {children}
            </div>
        </div>
    );
};
