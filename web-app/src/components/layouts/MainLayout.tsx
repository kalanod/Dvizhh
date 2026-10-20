import type { ReactNode } from "react";
import { CreateEventButton, PageHeader } from "../widgets";

interface MainLayoutProps {
    children: ReactNode;
    showCreateButton?: boolean;
}

export const MainLayout = ({ children, showCreateButton = true }: MainLayoutProps) => (
    <div className="relative flex w-full flex-col gap-5">
        <PageHeader />
        <div className="flex w-full flex-col">{children}</div>
        {showCreateButton && <CreateEventButton />}
    </div>
);
