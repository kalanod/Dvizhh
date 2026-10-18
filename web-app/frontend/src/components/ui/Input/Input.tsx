import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export type InputState = "default" | "error";

const stateClassMap: Record<InputState, string> = {
    default: "border-bordersoft focus:border-borderfocus",
    error: "border-bordererror text-texterror",
};

const baseClass =
    "w-full rounded-xl border-2 bg-primary px-4 text-body text-textprimary outline-none transition-colors placeholder:text-secondary disabled:opacity-60";

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "value"> {
    state?: InputState;
    value: string;
    onChange: (value: string) => void;
    errorMessage?: string;
}

export const Input = ({ state = "default", value, onChange, className = "", errorMessage, ...rest }: InputProps) => (
    <div className="flex w-full flex-col gap-1">
        <input
            {...rest}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            aria-invalid={state === "error"}
            className={`h-[41px] ${baseClass} ${stateClassMap[state]} ${className}`}
        />
        {state === "error" && errorMessage && <span className="text-small text-texterror">{errorMessage}</span>}
    </div>
);

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
        className={`resize-y py-2.5 ${baseClass} ${stateClassMap.default} ${className}`}
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
        <span className="pointer-events-none absolute top-1/2 right-4 -translate-y-1/2 text-textsecondary">▾</span>
    </div>
);
