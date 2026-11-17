import { useEffect, useRef, useState } from "react";
import { searchFriends } from "../api/users";
import type { Profile } from "../models";

interface PageState {
    key: string; items: Profile[]; offset: number; more: boolean; loading: boolean; error?: unknown;
}

export function useFriendOptions(userId: string, query: string, open: boolean) {
    const key = JSON.stringify([userId, query.trim()]);
    const [state, setState] = useState<PageState>();
    const active = useRef<{ key: string; controller: AbortController; loading: boolean } | null>(null);
    useEffect(() => {
        if (!open) return;
        const request = { key, controller: new AbortController(), loading: true };
        active.current = request;
        const timer = window.setTimeout(() => {
            const [actor, text] = JSON.parse(key) as [string, string];
            setState({ key, items: [], offset: 0, more: true, loading: true });
            void searchFriends(actor, text, 0, request.controller.signal).then((items) => {
                if (!request.controller.signal.aborted) setState({ key, items, offset: items.length, more: items.length === 20, loading: false });
            }).catch((error: unknown) => {
                if (!request.controller.signal.aborted) setState({ key, items: [], offset: 0, more: true, loading: false, error });
            }).finally(() => { request.loading = false; });
        }, 300);
        return () => { window.clearTimeout(timer); request.controller.abort(); };
    }, [key, open]);
    const current = state?.key === key ? state : undefined;
    const loadMore = (retry = false) => {
        const request = active.current;
        if (!open || !current || !current.more || current.loading || (current.error && !retry)
            || !request || request.key !== key || request.loading || request.controller.signal.aborted) return;
        request.loading = true;
        setState({ ...current, loading: true, error: undefined });
        void searchFriends(userId, query.trim(), current.offset, request.controller.signal).then((items) => {
            if (request.controller.signal.aborted) return;
            const merged = [...new Map([...current.items, ...items].map((item) => [item.id, item])).values()];
            setState({ key, items: merged, offset: current.offset + items.length, more: items.length === 20, loading: false });
        }).catch((error: unknown) => {
            if (!request.controller.signal.aborted) setState({ ...current, loading: false, error });
        }).finally(() => { request.loading = false; });
    };
    return { items: current?.items ?? [], loading: open && (!current || current.loading), error: current?.error, loadMore };
}
