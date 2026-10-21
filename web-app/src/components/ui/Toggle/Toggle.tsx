interface ToggleProps {
    label: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
    disabled?: boolean;
    hint?: string;
}

/** Булев фильтр в стиле Radiobutton шаблона: «○» — выключен, «+» — включён. */
export const Toggle = ({ label, checked, onChange, disabled = false, hint }: ToggleProps) => (
    <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        title={hint}
        onClick={() => onChange(!checked)}
        className={`flex w-full items-center gap-2.5 rounded-lg border px-2.5 py-1 text-left transition-all duration-200 ${
            checked
                ? "border-bordersuccess bg-success text-textthird"
                : "border-bordermain bg-transparent text-textsecondary hover:bg-borderlight/20"
        } ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
        <span className="flex h-6 w-6 items-center justify-center text-base font-medium">{checked ? "+" : "○"}</span>
        <span className={`flex-1 text-body ${checked ? "font-medium text-textthird" : "text-textsecondary"}`}>{label}</span>
    </button>
);
