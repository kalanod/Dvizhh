import type { ReactNode } from "react";
import { FieldContext } from "./context";

interface FormFieldProps {
    label: string;
    htmlFor?: string;
    hint?: string;
    required?: boolean;
    children: ReactNode;
    className?: string;
}

export const FormField = ({ label, htmlFor, hint, required = false, children, className = "" }: FormFieldProps) => (
    <FieldContext.Provider value={{ label, htmlFor, hint, required }}>
    <div className={`dvizh-form-field flex w-full flex-col items-start gap-2 ${className}`}>
        <label htmlFor={htmlFor} className="dvizh-field-label text-body text-textprimary">
            {label}
            {required && <span className="text-texterror"> *</span>}
        </label>
        {children}
        {hint && <span className="dvizh-field-hint text-duration text-textsecondary">{hint}</span>}
    </div>
    </FieldContext.Provider>
);
