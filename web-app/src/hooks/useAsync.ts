import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

interface AsyncState<T> {
    key: string;
    data?: T;
    error?: unknown;
}

/**
 * Загружает данные при изменении key. Пока результат для текущего key не получен,
 * loading = true; reload() перезапрашивает данные с тем же key.
 * Устаревший запрос (сменился key, компонент ушёл со страницы) отменяется через signal —
 * передайте его в функцию API, чтобы backend не обрабатывал ненужные ответы.
 */
export const useAsync = <T>(load: (signal: AbortSignal) => Promise<T>, key: string) => {
    const [state, setState] = useState<AsyncState<T> | null>(null);
    const [version, setVersion] = useState(0);
    const loadRef = useRef(load);
    const fullKey = `${key}#${version}`;

    useLayoutEffect(() => {
        loadRef.current = load;
    });

    useEffect(() => {
        const controller = new AbortController();
        const { signal } = controller;
        loadRef.current(signal).then(
            (data) => !signal.aborted && setState({ key: fullKey, data }),
            (error: unknown) => !signal.aborted && setState({ key: fullKey, error }),
        );
        return () => controller.abort();
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
