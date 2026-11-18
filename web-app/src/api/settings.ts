import type { SettingsActionResult, SettingsDocument, SettingsRowsValues } from "../models/settings";
import { request } from "./client";

export class SettingsProtocolError extends Error {}
const invalid = () => { throw new SettingsProtocolError("Формат настроек не поддерживается. Обновите страницу или приложение."); };
const object = (value: unknown): Record<string, unknown> => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
    return value as Record<string, unknown>;
};
const string = (value: unknown): value is string => typeof value === "string";
const id = (value: unknown): value is string => string(value) && /^[a-zA-Z0-9_.:-]{1,200}$/.test(value);
const optionalString = (value: unknown) => value === undefined || string(value);
const optionalLength = (value: unknown) => value === undefined || (Number.isSafeInteger(value) && Number(value) >= 0);

/** Reject unsupported versions/elements before showing any mutable controls. */
export function parseSettingsDocument(value: unknown): SettingsDocument {
    const document = object(value);
    if (document.schema_version !== 2 || !Array.isArray(document.tabs)) return invalid();
    const tabIds = new Set<string>();
    const cardIds = new Set<string>();
    const rowIds = new Set<string>();
    const actionIds = new Set<string>();
    const checkButton = (element: Record<string, unknown>) => {
        if (element.type !== "button" || !id(element.id) || !string(element.label) || !id(element.action_id) || actionIds.has(element.action_id) || typeof element.validate_fields !== "boolean" || !["all", "changed"].includes(String(element.rows)) || !["primary", "secondary", "danger"].includes(String(element.tone)) || !optionalString(element.confirmation)) return invalid();
        actionIds.add(element.action_id);
    };
    for (const rawTab of document.tabs) {
        const tab = object(rawTab);
        if (!id(tab.id) || tabIds.has(tab.id) || !string(tab.label) || !Array.isArray(tab.cards)) return invalid();
        tabIds.add(tab.id);
        for (const rawCard of tab.cards) {
            const card = object(rawCard);
            if (!id(card.id) || cardIds.has(card.id) || !optionalString(card.title) || !optionalString(card.description) || !Array.isArray(card.rows) || !Array.isArray(card.actions)) return invalid();
            cardIds.add(card.id);
            if (card.widget !== undefined && (card.widget !== "users" || card.rows.length || card.actions.length)) return invalid();
            const cardButtonIds = new Set<string>();
            for (const rawAction of card.actions) {
                const action = object(rawAction);
                checkButton(action);
                if (!id(action.id) || cardButtonIds.has(action.id)) return invalid();
                cardButtonIds.add(action.id);
            }
        for (const rawRow of card.rows) {
            const row = object(rawRow);
            if (!id(row.id) || rowIds.has(row.id) || !Array.isArray(row.elements)) return invalid();
            rowIds.add(row.id);
            const elementIds = new Set<string>();
            for (const rawElement of row.elements) {
                const element = object(rawElement);
                if (!id(element.id) || elementIds.has(element.id)) return invalid();
                elementIds.add(element.id);
                switch (element.type) {
                    case "text":
                        if (!string(element.text) || !["normal", "muted"].includes(String(element.tone))) return invalid();
                        break;
                    case "input":
                        if (!string(element.label) || !string(element.value) || !["text", "password"].includes(String(element.input_type)) || typeof element.required !== "boolean") return invalid();
                        if (![element.hint, element.matches, element.pattern, element.autocomplete].every(optionalString) || !optionalLength(element.min_length) || !optionalLength(element.max_length)) return invalid();
                        if (element.min_length !== undefined && element.max_length !== undefined && Number(element.min_length) > Number(element.max_length)) return invalid();
                        if (element.input_type === "password" && element.value !== "") return invalid();
                        if (element.pattern !== undefined) {
                            try { new RegExp(`^(?:${element.pattern})$`, "v"); } catch { return invalid(); }
                        }
                        break;
                    case "select": {
                        if (!string(element.label) || !string(element.value) || typeof element.required !== "boolean" || !Array.isArray(element.options)) return invalid();
                        const optionValues = new Set<string>();
                        for (const rawOption of element.options) {
                            const option = object(rawOption);
                            if (!string(option.value) || !string(option.label) || optionValues.has(option.value)) return invalid();
                            optionValues.add(option.value);
                        }
                        if (!optionValues.has(element.value) && (element.value !== "" || element.required)) return invalid();
                        break;
                    }
                    case "toggle":
                        if (!string(element.label) || typeof element.value !== "boolean" || !optionalString(element.hint)) return invalid();
                        break;
                    case "button":
                        checkButton(element);
                        if (element.rows !== "all") return invalid();
                        break;
                    default: return invalid();
                }
            }
            for (const rawElement of row.elements) {
                const element = object(rawElement);
                if (element.type === "input" && element.matches !== undefined && !row.elements.some((candidate: unknown) => {
                    const target = object(candidate);
                    return target.type === "input" && target.id === element.matches && target.id !== element.id;
                })) return invalid();
            }
        }
        }
    }
    return value as SettingsDocument;
}

export const getSettingsDocument = async (signal?: AbortSignal) =>
    parseSettingsDocument(await request<unknown>("/settings", { signal }));

export async function executeSettingsAction(actionId: string, rows: SettingsRowsValues, signal?: AbortSignal): Promise<SettingsActionResult> {
    if (!id(actionId)) return invalid();
    const result = object(await request<unknown>(`/settings/actions/${encodeURIComponent(actionId)}`, {
        method: "POST", headers: { "X-Dvizh-Admin": "1", "X-Dvizh-Account": "1" },
        body: { schema_version: 2, rows }, signal,
    }));
    if (result.schema_version !== 2 || !string(result.message) || !Array.isArray(result.applied_rows) || !result.applied_rows.every(id) || new Set(result.applied_rows).size !== result.applied_rows.length || result.applied_rows.length !== Object.keys(rows).length || result.applied_rows.some((rowId: string) => !Object.hasOwn(rows, rowId))) return invalid();
    return { schema_version: 2, message: result.message, document: parseSettingsDocument(result.document), applied_rows: result.applied_rows };
}
