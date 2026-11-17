import { useEffect, useMemo, useState } from "react";

export type AsyncFieldValidator = (value: string, signal: AbortSignal) => Promise<string | null>;

/** A result belongs to a value; abandoned requests never recolor newer input. */
export function useFieldValidation(value: string, enabled: boolean, validate?: AsyncFieldValidator) {
    const key = useMemo(() => ({ value, enabled, validate }), [value, enabled, validate]);
    const [result, setResult] = useState<{ key: typeof key; error: string | null; unavailable?: boolean }>();
    useEffect(() => {
        if (!key.enabled || !key.validate) return;
        const controller = new AbortController();
        const timer = window.setTimeout(() => {
            void key.validate!(key.value, controller.signal).then((error) => {
                if (!controller.signal.aborted) setResult({ key, error });
            }).catch(() => {
                if (!controller.signal.aborted) setResult({ key, error: null, unavailable: true });
            });
        }, 350);
        return () => { window.clearTimeout(timer); controller.abort(); };
    }, [key]);
    const current = result?.key === key ? result : undefined;
    return {
        pending: enabled && !!validate && !current,
        error: enabled ? current?.error : null,
        unavailable: enabled && current?.unavailable,
    };
}
