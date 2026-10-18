import type { ReactNode } from "react";

interface FormFieldProps {
    label: string;
    htmlFor?: string;
    hint?: string;
    required?: boolean;
    children: ReactNode;
    className?: string;
}

export const FormField = ({ label, htmlFor, hint, required = false, children, className = "" }: FormFieldProps) => (
    <div className={`flex w-full flex-col gap-1.5 ${className}`}>
        <label htmlFor={htmlFor} className="text-small text-textprimary">
            {label}
            {required && <span className="text-borderlight"> *</span>}
        </label>
        {children}
        {hint && <span className="text-small font-medium text-textsecondary">{hint}</span>}
    </div>
);
