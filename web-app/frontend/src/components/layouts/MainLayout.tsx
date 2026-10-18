import type { ReactNode } from "react";
import { CreateEventButton, PageHeader } from "../widgets";

interface MainLayoutProps {
    children: ReactNode;
    showCreateButton?: boolean;
}

export const MainLayout = ({ children, showCreateButton = true }: MainLayoutProps) => (
    <div className="relative flex w-full flex-col gap-5 pb-20">
        <PageHeader />
        <main className="flex w-full flex-col">{children}</main>
        {showCreateButton && <CreateEventButton />}
    </div>
);
