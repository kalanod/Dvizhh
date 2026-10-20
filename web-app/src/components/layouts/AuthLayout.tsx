import type { ReactNode } from "react";

interface AuthLayoutProps {
    title: string;
    children: ReactNode;
}

/** Центрированная карточка входа и регистрации, как LoginPage шаблона. */
export const AuthLayout = ({ title, children }: AuthLayoutProps) => (
    <div className="flex min-h-[calc(100svh-48px)] w-full items-center justify-center">
        <div className="rounded-lg sm:p-16">
            <div className="flex w-full max-w-[431px] flex-col items-start gap-2.5 rounded-lg bg-cards-surface p-8 sm:w-[431px] sm:p-16">
                <div className="flex w-full flex-col items-start gap-2.5">
                    <div className="flex w-full flex-col items-center justify-center self-stretch">
                        <h1 className="self-stretch text-center text-h1 text-textprimary">{title}</h1>
                    </div>
                    {children}
                </div>
            </div>
        </div>
    </div>
);
