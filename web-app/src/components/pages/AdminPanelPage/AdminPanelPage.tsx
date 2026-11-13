import { Navigate } from "react-router-dom";
import { errorText } from "../../../api";
import { useAdminAccess } from "../../../hooks/useAdminAccess";
import { MainLayout } from "../../layouts";
import { Button, Loader, Notice } from "../../ui";

export const AdminPanelPage = () => {
    const { allowed, loading, error, reload } = useAdminAccess();
    if (!loading && !error && !allowed) return <Navigate to="/" replace />;
    return (
        <MainLayout showCreateButton={false}>
            {loading ? <Loader /> : error ? (
                <div className="flex flex-col items-start gap-3">
                    <Notice tone="error">{errorText(error)}</Notice>
                    <Button onClick={reload}>Повторить проверку доступа</Button>
                </div>
            ) : (
                <h1 className="text-h1 text-textprimary">Настройки</h1>
            )}
        </MainLayout>
    );
};
