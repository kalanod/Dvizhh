import type { SettingsButton, SettingsRow as Row, SettingsValues } from "../../../models/settings";
import { Button, Input, Select, Toggle } from "../../ui";
import { SettingsField } from "./SettingsField";

interface Props {
    row: Row;
    values: SettingsValues;
    busy: boolean;
    onChange: (fieldId: string, value: string | boolean) => void;
    onAction: (button: SettingsButton) => void;
}

/** Primitive fields form one horizontal row; the enclosing card owns the form and its actions. */
export const SettingsRow = ({ row, values, busy, onChange, onAction }: Props) => (
    <fieldset disabled={busy} className="flex min-w-0 flex-nowrap items-end gap-4">
        {row.elements.map((element) => {
            const fieldId = `setting-${row.id}-${element.id}`;
            switch (element.type) {
                case "text": return <p key={element.id} className={`flex h-[56px] w-28 shrink-0 items-center text-body ${element.tone === "muted" ? "text-textsecondary" : "text-textprimary"}`}><span className="line-clamp-2 break-words" title={element.text}>{element.text}</span></p>;
                case "input": return <SettingsField key={element.id} id={fieldId} label={element.label} hint={element.hint} required={element.required}>
                    <Input id={fieldId} name={element.id} type={element.input_type} required={element.required} minLength={element.min_length} maxLength={element.max_length} pattern={element.pattern} validate={element.matches ? (value) => value === String(values[element.matches!] ?? "") ? null : "Значения не совпадают." : undefined} autoComplete={element.autocomplete ?? "off"} value={String(values[element.id] ?? "")} onChange={(value) => onChange(element.id, value)} />
                </SettingsField>;
                case "select": return <SettingsField key={element.id} id={fieldId} label={element.label} required={element.required}>
                    <Select id={fieldId} name={element.id} required={element.required} value={String(values[element.id] ?? "")} options={Object.fromEntries(element.options.map((option) => [option.value, option.label]))} onChange={(value) => onChange(element.id, value)} />
                </SettingsField>;
                case "toggle": return <div key={element.id} className="h-[41px] w-28 shrink-0 [&_button]:h-full"><Toggle label={element.label} hint={element.hint} checked={values[element.id] === true} disabled={busy} onChange={(value) => onChange(element.id, value)} /></div>;
                case "button": return <Button key={element.id} disabled={busy} state={element.tone === "primary" ? "hover1" : "hover2"} className={element.tone === "danger" ? "!border-bordererror !bg-primary !text-texterror" : ""} onClick={() => onAction(element)}>{element.label}</Button>;
            }
        })}
    </fieldset>
);
