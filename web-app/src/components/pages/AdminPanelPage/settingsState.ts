import type { SettingsButton, SettingsCard, SettingsDocument, SettingsElement, SettingsField, SettingsRow, SettingsRowsValues, SettingsValues } from "../../../models/settings";

export const isSettingsField = (element: SettingsElement): element is SettingsField =>
    element.type === "input" || element.type === "select" || element.type === "toggle";
export const isSecretField = (field: SettingsField) => field.type === "input" && field.input_type === "password";
export const rowValues = (row: SettingsRow): SettingsValues => Object.fromEntries(
    row.elements.filter(isSettingsField).map((field) => [field.id, field.value]),
);

export type SettingsDrafts = Record<string, SettingsValues>;

/** Preserve independent edits only while their field and allowed value still exist. Never retain secrets. */
export function reconcileSettingsDrafts(next: SettingsDocument, drafts: SettingsDrafts, completedRows: string[] = []): SettingsDrafts {
    const result: SettingsDrafts = {};
    for (const tab of next.tabs) for (const card of tab.cards) for (const row of card.rows) {
        if (completedRows.includes(row.id)) continue;
        const previous = drafts[row.id];
        if (!previous) continue;
        const retained: SettingsValues = {};
        for (const field of row.elements.filter(isSettingsField)) {
            const value = previous[field.id];
            if (value === undefined || isSecretField(field) || typeof value !== typeof field.value || value === field.value) continue;
            if (field.type === "select" && !field.options.some((option) => option.value === value)) continue;
            retained[field.id] = value;
        }
        if (Object.keys(retained).length) result[row.id] = retained;
    }
    return result;
}

/** Actions submit whole rows; edit-card actions include only rows with actual changed values. */
export function cardActionRows(card: SettingsCard, action: SettingsButton, drafts: SettingsDrafts, secrets: SettingsRowsValues = {}): SettingsRowsValues {
    const result: SettingsRowsValues = {};
    for (const row of card.rows) {
        const base = rowValues(row);
        if (!Object.keys(base).length) continue;
        const current = { ...base, ...drafts[row.id], ...secrets[row.id] };
        const changed = Object.keys(base).some((key) => current[key] !== base[key]);
        if (action.rows === "all" || changed) result[row.id] = current;
    }
    return result;
}

export function validateSettingsValues(row: SettingsRow, values: SettingsValues): string | null {
    for (const field of row.elements.filter(isSettingsField)) {
        const value = values[field.id];
        if (field.type === "toggle") {
            if (typeof value !== "boolean") return `Проверьте поле «${field.label}».`;
        } else if (typeof value !== "string") return `Проверьте поле «${field.label}».`;
        else if (field.type === "select") {
            if (!field.options.some((option) => option.value === value) && (field.required || value !== "")) return `Выберите значение в поле «${field.label}».`;
        } else {
            if (field.required && !value) return `Заполните поле «${field.label}».`;
            if (field.min_length !== undefined && value.length < field.min_length) return `Поле «${field.label}»: минимум ${field.min_length} символов.`;
            if (field.max_length !== undefined && value.length > field.max_length) return `Поле «${field.label}»: максимум ${field.max_length} символов.`;
            if (field.pattern && !new RegExp(`^(?:${field.pattern})$`, "v").test(value)) return `Проверьте формат поля «${field.label}».`;
            if (field.matches && value !== values[field.matches]) return `Поле «${field.label}» не совпадает с подтверждаемым значением.`;
        }
    }
    return null;
}
