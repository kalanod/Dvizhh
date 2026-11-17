import { createContext } from "react";

export const FieldContext = createContext<{ label: string; htmlFor?: string; hint?: string; required: boolean } | null>(null);
