import { Navigate } from "react-router-dom";
import { errorText } from "../../../api";
import { useAdminAccess } from "../../../hooks/useAdminAccess";
import { MainLayout } from "../../layouts";
import { Button, Loader, Notice } from "../../ui";
import { getSettingsDocument } from "../../../api/settings";
import { useAsync } from "../../../hooks/useAsync";
import { SettingsWorkspace } from "./SettingsWorkspace";

export const AdminPanelPage = () => {
    const { allowed, loading, error, reload } = useAdminAccess();
    if (!loading && !error && !allowed) return <Navigate to="/" replace />;
    return (
        <MainLayout showCreateButton={false} fitViewport>
            {loading ? <Loader /> : error ? (
                <div className="flex flex-col items-start gap-3">
                    <Notice tone="error">{errorText(error)}</Notice>
                    <Button onClick={reload}>Повторить проверку доступа</Button>
                </div>
            ) : (
                <SettingsContent />
            )}
        </MainLayout>
    );
};

const SettingsContent = () => {
    const state = useAsync(getSettingsDocument, "settings-document");
    if (state.loading) return <Loader text="Загружаем настройки…" />;
    if (state.error || !state.data) return <div className="flex flex-col items-start gap-3">
        <Notice tone="error">{errorText(state.error)}</Notice>
        <Button onClick={state.reload}>Загрузить настройки заново</Button>
    </div>;
    return <SettingsWorkspace initialDocument={state.data} onAccessLost={state.reload} />;
};
