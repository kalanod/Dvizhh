import type { ReactNode } from "react";
import { CreateEventButton, PageHeader } from "../widgets";

interface MainLayoutProps {
    children: ReactNode;
    showCreateButton?: boolean;
    fitViewport?: boolean;
}

export const MainLayout = ({ children, showCreateButton = true, fitViewport = false }: MainLayoutProps) => (
    <div className={fitViewport ? "fixed inset-0 mx-auto flex w-full max-w-[1600px] flex-col gap-5 overflow-hidden p-2.5 sm:p-4 lg:p-6" : "relative flex w-full flex-col gap-5"}>
        {fitViewport ? <div className="shrink-0"><PageHeader /></div> : <PageHeader />}
        <div className={`flex w-full flex-col ${fitViewport ? "min-h-0 flex-1 overflow-hidden" : ""} ${showCreateButton ? "pb-16" : ""}`}>{children}</div>
        {showCreateButton && <CreateEventButton />}
    </div>
);
