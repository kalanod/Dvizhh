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
    <div className={`flex w-full flex-col items-start gap-2 ${className}`}>
        <label htmlFor={htmlFor} className="text-body text-textprimary">
            {label}
            {required && <span className="text-texterror"> *</span>}
        </label>
        {children}
        {hint && <span className="text-duration text-textsecondary">{hint}</span>}
    </div>
);
