import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../../api/client";
import { executeSettingsAction, SettingsProtocolError } from "../../../api/settings";
import type { SettingsDocument, SettingsRowsValues } from "../../../models/settings";
import { Notice } from "../../ui";
import { SettingsCardForm } from "./SettingsCardForm";
import { reconcileSettingsDrafts, type SettingsDrafts } from "./settingsState";

export const SettingsWorkspace = ({ initialDocument, onAccessLost }: { initialDocument: SettingsDocument; onAccessLost: () => void }) => {
    const [document, setDocument] = useState(initialDocument);
    const [activeTab, setActiveTab] = useState(initialDocument.tabs[0]?.id ?? "");
    const [drafts, setDrafts] = useState<SettingsDrafts>({});
    const [busy, setBusy] = useState(false);
    const [uncertain, setUncertain] = useState(false);
    const request = useRef<AbortController | null>(null);
    const panel = useRef<HTMLDivElement>(null);
    useEffect(() => () => request.current?.abort(), []);
    const selected = document.tabs.find((tab) => tab.id === activeTab) ?? document.tabs[0];
    const execute = async (actionId: string, rows: SettingsRowsValues) => {
        if (request.current) throw new Error("Дождитесь завершения сохранения.");
        const controller = new AbortController();
        request.current = controller; setBusy(true);
        try {
            const result = await executeSettingsAction(actionId, rows, controller.signal);
            if (controller.signal.aborted) throw new Error("Сохранение прервано. Обновите страницу, чтобы проверить результат.");
            setDocument(result.document);
            setDrafts((previous) => reconcileSettingsDrafts(result.document, previous, result.applied_rows));
            return result.message;
        } catch (error) {
            if (error instanceof SettingsProtocolError || (error instanceof ApiError && (error.status === 401 || error.status === 403))) onAccessLost();
            if (error instanceof ApiError && (error.status === 0 || error.status >= 500)) setUncertain(true);
            throw error;
        } finally {
            request.current = null;
            if (!controller.signal.aborted) setBusy(false);
        }
    };
    return <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-hidden lg:flex-row">
        <nav aria-label="Разделы настроек" className="flex shrink-0 flex-wrap gap-2 rounded-lg bg-cards-surface p-3 lg:w-52 lg:flex-col">
            {document.tabs.map((tab) => <button key={tab.id} type="button" aria-pressed={selected?.id === tab.id} disabled={busy} onClick={() => { setActiveTab(tab.id); panel.current?.scrollTo({ top: 0 }); }} className={`min-w-0 rounded-lg border-2 px-4 py-3 text-left text-body break-words transition-colors disabled:opacity-50 ${selected?.id === tab.id ? "border-bordermain bg-borderlight text-textprimary" : "border-transparent text-textprimary hover:bg-borderlight/40"}`}>{tab.label}</button>)}
        </nav>
        <section ref={panel} tabIndex={0} aria-label={selected?.label ?? "Настройки"} aria-busy={busy} className="min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain rounded-lg outline-offset-[-2px]">
            {uncertain && <Notice tone="error" className="mb-4">Сервер не подтвердил результат сохранения. Перезагрузите страницу перед повтором; несохранённый ввод будет сброшен.</Notice>}
            {selected ? <>
                <div aria-label={`Карточки настроек: ${selected.label}`} className="flex min-w-0 flex-col gap-4">
                    {selected.cards.length ? selected.cards.map((card) => <SettingsCardForm key={`${selected.id}:${card.id}`} card={card} drafts={drafts} busy={busy || uncertain} onChange={(rowId, fieldId, value) => setDrafts((previous) => ({ ...previous, [rowId]: { ...previous[rowId], [fieldId]: value } }))} onExecute={execute} />) : <Notice>В этом разделе пока нет настроек.</Notice>}
                </div>
            </> : <Notice>Нет доступных разделов настроек.</Notice>}
        </section>
    </div>;
};
