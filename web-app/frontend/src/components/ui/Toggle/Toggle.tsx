interface ToggleProps {
    label: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
    disabled?: boolean;
    hint?: string;
}

/** Переключатель «вкл/выкл»: заменяет трёхпозиционный Radiobutton шаблона для булевых фильтров. */
export const Toggle = ({ label, checked, onChange, disabled = false, hint }: ToggleProps) => (
    <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        title={hint}
        onClick={() => onChange(!checked)}
        className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left text-body transition-colors ${
            checked
                ? "border-bordermain bg-bordermain/10 text-textprimary"
                : "border-bordersoft bg-primary text-textsecondary hover:border-bordermain/50"
        } ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
        <span>{label}</span>
        <span
            className={`relative h-[22px] w-[38px] shrink-0 rounded-full transition-colors ${checked ? "bg-bordermain" : "bg-secondary/40"}`}
        >
            <span
                className={`absolute top-[3px] h-4 w-4 rounded-full bg-primary transition-all ${checked ? "left-[19px]" : "left-[3px]"}`}
            />
        </span>
    </button>
);
