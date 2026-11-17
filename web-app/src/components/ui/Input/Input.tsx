import { useState, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

export type InputState = "default" | "error";

const stateClassMap: Record<InputState, string> = {
    default: "border-secondary bg-primary text-textprimary focus:border-borderfocus",
    error: "border-bordererror bg-primary text-texterror",
};

const baseClass = "w-full rounded-lg border-2 px-4 text-body outline-none transition-all disabled:opacity-50";

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
    state?: InputState;
    value: string;
    onChange: (value: string) => void;
    errorMessage?: string;
}

export const Input = ({ state = "default", value, onChange, className = "", errorMessage, type = "text", ...rest }: InputProps) => {
    const [revealed, setRevealed] = useState(false);
    const isPassword = type === "password";

    return (
        <div className="flex w-full flex-col gap-1">
            <div className="relative w-full">
                <input
                    {...rest}
                    type={isPassword && revealed ? "text" : type}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    onBlur={(e) => {
                        setRevealed(false);
                        rest.onBlur?.(e);
                    }}
                    aria-invalid={state === "error"}
                    className={`h-[41px] py-2 ${baseClass} ${stateClassMap[state]} ${isPassword ? "pr-11" : ""} ${className}`}
                />
                {isPassword && <PasswordPeek revealed={revealed} onReveal={setRevealed} disabled={rest.disabled} />}
            </div>
            {state === "error" && errorMessage && <span className="text-small text-texterror">{errorMessage}</span>}
        </div>
    );
};

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

interface TextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, "onChange" | "value"> {
    value: string;
    onChange: (value: string) => void;
}

export const Textarea = ({ value, onChange, className = "", rows = 4, ...rest }: TextareaProps) => (
    <textarea
        {...rest}
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`resize-y py-2 ${baseClass} ${stateClassMap.default} ${className}`}
    />
);

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
