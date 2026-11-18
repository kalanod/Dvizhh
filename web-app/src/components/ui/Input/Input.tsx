import { useContext, useId, useState, type DOMAttributes, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import { FieldContext } from "../FormField/context";
import { useFieldValidation, type AsyncFieldValidator } from "../../../hooks/useFieldValidation";

export type InputState = "default" | "error" | "success";
const stateClassMap = { default: "border-secondary bg-primary text-textprimary" };
const baseClass = "w-full rounded-lg border-2 px-4 text-body outline-none transition-all disabled:opacity-50";

type ValidationProps = {
    state?: InputState;
    errorMessage?: string;
    errorDisplay?: "tooltip" | "inline";
    validate?: (value: string) => string | null;
    validateAsync?: AsyncFieldValidator;
    successMessage?: string;
    variant?: "floating" | "compact";
};
interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value">, ValidationProps {
    value: string;
    onChange: (value: string) => void;
}

export const Input = (props: InputProps) => <TextControl {...props} />;

interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value">, ValidationProps {
    value: string;
    onChange: (value: string) => void;
}
export const Textarea = (props: TextareaProps) => <TextControl {...props} multiline />;

type ControlProps = Omit<InputProps, keyof DOMAttributes<HTMLInputElement>> & Omit<DOMAttributes<HTMLInputElement | HTMLTextAreaElement>, "onChange"> & {
    onChange: (value: string) => void;
    multiline?: boolean;
    rows?: number;
};
function TextControl({ state = "default", value, onChange, className = "", errorMessage,
    type = "text", variant, validate, validateAsync, successMessage, multiline, rows = 4, onFocus, onBlur, onInvalid, errorDisplay = "tooltip", ...rest }: ControlProps) {
    const field = useContext(FieldContext);
    const context = field && (!field.htmlFor || rest.id === field.htmlFor) ? field : null;
    const floating = (variant ?? (context ? "floating" : "compact")) === "floating";
    const [revealed, setRevealed] = useState(false);
    const [focused, setFocused] = useState(false);
    const [touched, setTouched] = useState(false);
    const [nativeError, setNativeError] = useState<{ value: string; message: string } | null>(null);
    const statusId = useId();
    const required = rest.required ?? context?.required;
    const isPassword = type === "password";
    const localError = fieldError(value, { ...rest, type, required }, validate);
    const remote = useFieldValidation(value, !!value && !localError && !rest.disabled && !rest.readOnly, validateAsync);
    const error = state === "error" ? errorMessage || "Проверьте значение." : (value || touched) ? localError || (nativeError?.value === value ? nativeError.message : null) || remote.error : null;
    const success = !error && !!value && !remote.pending && !remote.unavailable && state !== "error" && (floating || state === "success");
    const status = error ? "error" : remote.pending ? "pending" : remote.unavailable ? "unavailable" : success ? "success" : "default";
    const message = error || (remote.pending ? "Проверяем…" : remote.unavailable ? "Не удалось проверить. Проверим при сохранении." : successMessage && success ? successMessage : context?.hint);
    const temporal = ["date", "datetime-local", "time", "month", "week"].includes(type);
    const color = error ? "var(--color-bordererror)" : success ? "#25834b" : remote.pending ? "var(--color-borderfocus)" : "var(--color-secondary)";
    const label = context?.label ?? rest["aria-label"] ?? rest.placeholder;
    const tooltip = error && errorDisplay === "inline" ? "" : message;
    return <Tooltip title={tooltip || ""} placement="top-start" arrow open={focused && !!tooltip} onClose={() => setFocused(false)} disableHoverListener disableTouchListener>
        <div className={`dvizh-text-control relative w-full ${floating ? "dvizh-floating" : ""} ${className}`} data-validation={status}>
            <TextField
                id={rest.id} name={rest.name} type={isPassword && revealed ? "text" : type}
                value={value} onChange={(event) => { setNativeError(null); onChange(event.target.value); }}
                onFocus={(event) => { setFocused(true); onFocus?.(event); }}
                onBlur={(event) => { setFocused(false); setTouched(true); setRevealed(false); onBlur?.(event); }}
                label={floating ? label : undefined} placeholder={floating ? undefined : rest.placeholder ?? label}
                variant="filled" fullWidth hiddenLabel={!floating} size={floating ? "medium" : "small"}
                multiline={multiline} rows={multiline ? rows : undefined} required={required} disabled={rest.disabled}
                error={!!error}
                helperText={errorDisplay === "inline" ? error : undefined}
                inputRef={(node: HTMLInputElement | HTMLTextAreaElement | null) => node?.setCustomValidity(error || "")}
                slotProps={{
                    htmlInput: { ...rest, required, onInvalid: (event: React.InvalidEvent<HTMLInputElement | HTMLTextAreaElement>) => {
                        setTouched(true);
                        if (!event.currentTarget.validity.customError) setNativeError({ value, message: event.currentTarget.validationMessage });
                        onInvalid?.(event);
                    }, "aria-label": rest["aria-label"] ?? label, "aria-invalid": !!error, "aria-describedby": [rest["aria-describedby"], statusId, errorDisplay === "inline" && error ? `${statusId}-error` : null].filter(Boolean).join(" ") },
                    inputLabel: { shrink: floating && temporal ? true : undefined },
                    input: { disableUnderline: true },
                    formHelperText: { id: `${statusId}-error` },
                }}
                sx={{
                    fontFamily: "inherit",
                    "& .MuiFilledInput-root": { fontFamily: "inherit", fontSize: "16px", color: "var(--color-textprimary)", backgroundColor: "var(--color-primary)", border: `2px solid ${color}`, borderRadius: "8px", transition: "border-color 180ms, box-shadow 180ms", overflow: "hidden", minHeight: floating ? "56px" : "41px", paddingRight: isPassword ? "36px" : undefined },
                    "& .MuiFilledInput-root:hover": { backgroundColor: "var(--color-primary)" },
                    "& .MuiFilledInput-root.Mui-focused": { backgroundColor: "var(--color-primary)", borderColor: error || success ? color : "var(--color-borderfocus)", boxShadow: `0 0 0 2px color-mix(in srgb, ${color} 12%, transparent)` },
                    "& .MuiInputLabel-root": { fontFamily: "inherit", color: error ? "var(--color-texterror)" : "var(--color-textprimary)", maxWidth: isPassword ? "calc(100% - 52px)" : "calc(100% - 24px)" },
                    "& .MuiInputLabel-root.Mui-focused": { color: error ? "var(--color-texterror)" : "var(--color-textprimary)" },
                    "& .MuiInputBase-input": { minWidth: 0 },
                    "& .MuiInputBase-input::placeholder": { color: "var(--color-textsecondary)", opacity: 1 },
                    "& .MuiFilledInput-root:not(.MuiInputBase-multiline)": { height: floating ? "56px" : "41px" },
                    "& .MuiInputBase-input:not(textarea)": { boxSizing: "border-box", height: "100%", padding: floating ? "23px 12px 6px" : "8px 12px" },
                }}
            />
            {isPassword && <PasswordPeek revealed={revealed} onReveal={setRevealed} disabled={rest.disabled} />}
            <span id={statusId} className="sr-only" role="status" aria-live="polite">{message}</span>
        </div>
    </Tooltip>;
}

function fieldError(value: string, props: Pick<InputProps, "type" | "required" | "minLength" | "maxLength" | "pattern" | "min" | "max" | "step">, validate?: (value: string) => string | null): string | null {
    if (!value) return props.required ? "Заполните поле." : validate?.(value) ?? null;
    if (props.required && props.type !== "password" && !value.trim()) return "Заполните поле.";
    if (props.minLength && value.length < props.minLength) return `Минимум ${props.minLength} символов.`;
    if (props.maxLength && value.length > props.maxLength) return `Максимум ${props.maxLength} символов.`;
    if (props.pattern && !new RegExp(`^(?:${props.pattern})$`, "v").test(value)) return "Проверьте формат значения.";
    // The browser remains the source of truth for native email, URL and number constraints.
    if (typeof document !== "undefined") {
        const input = document.createElement("input");
        for (const key of ["type", "min", "max", "step"] as const) {
            if (props[key] !== undefined) input.setAttribute(key, String(props[key]));
        }
        input.value = value;
        if (!input.validity.valid) return input.validationMessage || "Проверьте формат значения.";
    }
    return validate?.(value) ?? null;
}

interface PasswordPeekProps {
    revealed: boolean;
    onReveal: (revealed: boolean) => void;
    disabled?: boolean;
}

/** Глазик в поле пароля: пароль виден, только пока кнопку удерживают мышью, пальцем или клавишей. */
const PasswordPeek = ({ revealed, onReveal, disabled }: PasswordPeekProps) => {
    const hide = () => onReveal(false);
    const isRevealKey = (key: string) => key === " " || key === "Enter";

    return (
        <button
            type="button"
            disabled={disabled}
            aria-label="Показать пароль, пока кнопка нажата"
            aria-pressed={revealed}
            title="Удерживайте, чтобы увидеть пароль"
            // preventDefault оставляет фокус и курсор в поле ввода.
            onPointerDown={(e) => {
                e.preventDefault();
                onReveal(true);
            }}
            onPointerUp={hide}
            onPointerLeave={hide}
            onPointerCancel={hide}
            onKeyDown={(e) => {
                if (!isRevealKey(e.key)) return;
                e.preventDefault();
                onReveal(true);
            }}
            onKeyUp={(e) => isRevealKey(e.key) && hide()}
            onBlur={hide}
            // Долгое нажатие на телефоне иначе открывает контекстное меню.
            onContextMenu={(e) => e.preventDefault()}
            className="absolute top-1/2 right-2 flex h-8 w-8 -translate-y-1/2 cursor-pointer touch-none select-none items-center justify-center rounded-md text-textsecondary transition hover:text-textprimary disabled:cursor-not-allowed disabled:opacity-50"
        >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <path
                    d="M2 12C3.8 7.8 7.6 5 12 5C16.4 5 20.2 7.8 22 12C20.2 16.2 16.4 19 12 19C7.6 19 3.8 16.2 2 12Z"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinejoin="round"
                />
                <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
                {!revealed && <path d="M4 4L20 20" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />}
            </svg>
        </button>
    );
};

interface SelectProps<T extends string> extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "value"> {
    value: T;
    onChange: (value: T) => void;
    options: Record<T, string>;
}

export const Select = <T extends string>({ value, onChange, options, className = "", ...rest }: SelectProps<T>) => (
    <div className="relative w-full">
        <select
            {...rest}
            value={value}
            onChange={(e) => onChange(e.target.value as T)}
            className={`h-[41px] cursor-pointer pr-10 ${baseClass} ${stateClassMap.default} ${className}`}
        >
            {(Object.entries(options) as [T, string][]).map(([key, label]) => (
                <option key={key} value={key}>
                    {label}
                </option>
            ))}
        </select>
        <span className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-[11px] text-textsecondary">▼</span>
    </div>
);
