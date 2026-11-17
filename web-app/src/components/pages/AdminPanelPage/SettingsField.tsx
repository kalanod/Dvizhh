import type { ReactNode } from "react";
import { FormField } from "../../ui";

/** Text controls own their MUI focus tooltip and never change the row height. */
export const SettingsField = ({ id, label, hint, required, children }: {
    id: string; label: string; hint?: string; required?: boolean; children: ReactNode;
}) => <div className="w-36 min-w-32 flex-1">
    <FormField label={label} htmlFor={id} hint={hint} required={required}>{children}</FormField>
</div>;