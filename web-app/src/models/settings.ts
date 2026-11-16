export interface SettingsText {
    id: string; type: "text"; text: string; tone: "normal" | "muted";
}
export interface SettingsInput {
    id: string; type: "input"; label: string; value: string; input_type: "text" | "password";
    required: boolean; min_length?: number; max_length?: number; pattern?: string;
    hint?: string; matches?: string; autocomplete?: string;
}
export interface SettingsSelect {
    id: string; type: "select"; label: string; value: string;
    options: { value: string; label: string }[]; required: boolean;
}
export interface SettingsToggle {
    id: string; type: "toggle"; label: string; value: boolean; hint?: string;
}
export interface SettingsButton {
    id: string; type: "button"; label: string; action_id: string;
    tone: "primary" | "secondary" | "danger"; validate_fields: boolean;
    rows: "all" | "changed"; confirmation?: string;
}
export type SettingsField = SettingsInput | SettingsSelect | SettingsToggle;
export type SettingsElement = SettingsText | SettingsField | SettingsButton;
export interface SettingsRow { id: string; elements: SettingsElement[] }
export interface SettingsCard {
    id: string; title?: string; description?: string; rows: SettingsRow[]; actions: SettingsButton[];
}
export interface SettingsTab { id: string; label: string; cards: SettingsCard[] }
export interface SettingsDocument { schema_version: 2; tabs: SettingsTab[] }
export type SettingsValues = Record<string, string | boolean>;
export type SettingsRowsValues = Record<string, SettingsValues>;
export interface SettingsActionResult {
    schema_version: 2; message: string; document: SettingsDocument; applied_rows: string[];
}
