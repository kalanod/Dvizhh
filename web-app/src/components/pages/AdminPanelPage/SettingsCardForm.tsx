import { useRef, useState } from "react";
import { errorText } from "../../../api/client";
import type { SettingsButton, SettingsCard, SettingsRow as Row, SettingsRowsValues } from "../../../models/settings";
import { Button, Notice } from "../../ui";
import { SettingsRow } from "./SettingsRow";
import { cardActionRows, isSecretField, isSettingsField, rowValues, type SettingsDrafts, validateSettingsValues } from "./settingsState";

interface Props {
    card: SettingsCard;
    drafts: SettingsDrafts;
    busy: boolean;
    onChange: (rowId: string, fieldId: string, value: string | boolean) => void;
    onExecute: (actionId: string, rows: SettingsRowsValues) => Promise<string>;
}

export const SettingsCardForm = ({ card, drafts, busy, onChange, onExecute }: Props) => {
    const [secrets, setSecrets] = useState<SettingsRowsValues>({});
    const [feedback, setFeedback] = useState<{ text: string; error: boolean; rowId?: string } | null>(null);
    const submitting = useRef(false);
    const valuesFor = (row: Row) => ({ ...rowValues(row), ...drafts[row.id], ...secrets[row.id] });
    const change = (row: Row, fieldId: string, value: string | boolean) => {
        setFeedback(null);
        const field = row.elements.filter(isSettingsField).find((element) => element.id === fieldId);
        if (field && isSecretField(field)) setSecrets((previous) => ({ ...previous, [row.id]: { ...previous[row.id], [fieldId]: value } }));
        else onChange(row.id, fieldId, value);
    };
    const run = async (button: SettingsButton, row?: Row) => {
        if (busy || submitting.current) return;
        setFeedback(null);
        const payload = row ? { [row.id]: valuesFor(row) } : cardActionRows(card, button, drafts, secrets);
        const rowIds = Object.keys(payload);
        if (!rowIds.length) return;
        if (rowIds.length > 500) { setFeedback({ text: "За одно сохранение можно изменить не более 500 строк.", error: true }); return; }
        if (button.validate_fields) {
            for (const target of card.rows.filter((candidate) => Object.hasOwn(payload, candidate.id))) {
                const validation = validateSettingsValues(target, payload[target.id]);
                if (validation) { setFeedback({ text: validation, error: true, rowId: target.id }); return; }
            }
        }
        if (button.confirmation && !window.confirm(button.confirmation)) return;
        submitting.current = true;
        try { setFeedback({ text: await onExecute(button.action_id, payload), error: false }); }
        catch (failure) { setFeedback({ text: errorText(failure), error: true, rowId: row?.id }); }
        finally { submitting.current = false; setSecrets({}); }
    };
    const primaryAction = card.actions.find((action) => action.validate_fields);
    return <form noValidate aria-label={card.title ?? "Карточка настроек"} data-settings-card={card.id} onSubmit={(event) => { event.preventDefault(); if (primaryAction) void run(primaryAction); }} className="w-full min-w-max rounded-lg bg-cards-surface p-4 sm:p-5">
        {(card.title || card.actions.length > 0) && <header className="mb-4 flex max-w-[calc(100vw-4rem)] flex-wrap items-center gap-4">
            {card.title && <h2 className="text-h2 text-textprimary">{card.title}</h2>}
            <div className="flex flex-wrap gap-2">
                {card.actions.map((action) => <Button key={action.id} type={action.id === primaryAction?.id ? "submit" : "button"} disabled={busy || !Object.keys(cardActionRows(card, action, drafts, secrets)).length} state={action.tone === "primary" ? "hover1" : "hover2"} className={action.tone === "danger" ? "!border-bordererror !bg-primary !text-texterror" : ""} onClick={action.id === primaryAction?.id ? undefined : () => void run(action)}>{action.label}</Button>)}
            </div>
        </header>}
        {card.description && <p className="mb-4 max-w-[calc(100vw-4rem)] text-body text-textprimary">{card.description}</p>}
        <div className="flex flex-col gap-3">
            {card.rows.length ? card.rows.map((row) => <div key={row.id} className="min-w-max rounded-lg border border-borderlight p-3">
                <SettingsRow row={row} values={valuesFor(row)} busy={busy} onChange={(fieldId, value) => change(row, fieldId, value)} onAction={(action) => void run(action, row)} />
                {feedback?.rowId === row.id && <Notice tone="error" className="mt-3">{feedback.text}</Notice>}
            </div>) : <Notice>Пока нет записей.</Notice>}
        </div>
        {feedback && !feedback.rowId && <Notice tone={feedback.error ? "error" : "success"} className="mt-3">{feedback.text}</Notice>}
    </form>;
};
