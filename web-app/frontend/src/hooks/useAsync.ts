import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

interface AsyncState<T> {
    key: string;
    data?: T;
    error?: unknown;
}

/**
 * Загружает данные при изменении key. Пока результат для текущего key не получен,
 * loading = true; reload() перезапрашивает данные с тем же key.
 */
export const useAsync = <T>(load: () => Promise<T>, key: string) => {
    const [state, setState] = useState<AsyncState<T> | null>(null);
    const [version, setVersion] = useState(0);
    const loadRef = useRef(load);
    const fullKey = `${key}#${version}`;

    useLayoutEffect(() => {
        loadRef.current = load;
    });

    useEffect(() => {
        let cancelled = false;
        loadRef.current().then(
            (data) => !cancelled && setState({ key: fullKey, data }),
            (error: unknown) => !cancelled && setState({ key: fullKey, error }),
        );
        return () => {
            cancelled = true;
        };
    }, [fullKey]);

    const reload = useCallback(() => setVersion((value) => value + 1), []);
    const current = state?.key === fullKey ? state : null;

    return {
        data: current?.data,
        error: current?.error,
        loading: current === null,
        reload,
    };
};
