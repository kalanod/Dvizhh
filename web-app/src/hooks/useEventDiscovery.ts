import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError, errorText } from "../api/client";
import { refreshDiscoverySession } from "../api/discovery";
import type { DiscoveryMapItem, DiscoveryRequest, DiscoveryResponse, DiscoverySort, DiscoveryViewport } from "../api/discovery";
import type { DvizhEvent } from "../models";
import { discoveryCache, mergeDiscoveryEvents } from "../utils/discovery";
import { currentCoordinates } from "../utils/geolocation";
import { useCurrentUser } from "./useCurrentUser";
import { useEventFilters } from "./useEventFilters";

interface Result {
    key: string; requestKey: string; userId: string | null;
    events: DvizhEvent[]; map: DiscoveryResponse["map"]; total?: number; next: string | null;
    mapViewport: DiscoveryViewport | null;
    refreshAfterSeconds?: number;
    error?: unknown;
}

/** One owner for the map, filters, selected region and feed pagination. */
export function useEventDiscovery(isFeedRoute: boolean) {
    const { userId, user, loading: userLoading } = useCurrentUser();
    const filterState = useEventFilters(isFeedRoute);
    const { filters } = filterState;
    const [viewport, setViewport] = useState<DiscoveryViewport | null>(null);
    const [mapCollapsed, setMapCollapsed] = useState(false);
    const [sortChoice, changeSort] = useState<{ actorId: string | null; value: DiscoverySort } | null>(null);
    const [point, setPoint] = useState<{ actorId: string | null; latitude: number; longitude: number } | null>(null);
    const [sortNotice, setSortNotice] = useState<string | null>(null);
    const sortRequest = useRef(0);
    const actor = useRef(userId);
    useLayoutEffect(() => { actor.current = userId; sortRequest.current++; }, [userId]);
    useEffect(() => () => { sortRequest.current++; }, []);
    const sort = sortChoice?.actorId === userId ? sortChoice.value : userId ? "relevance" : "novelty";
    const origin = point?.actorId === userId ? { latitude: point.latitude, longitude: point.longitude } : null;
    const [selection, setSelection] = useState<{ scope: string; item: DiscoveryMapItem } | null>(null);
    const [page, setPage] = useState<{ key: string; cursor: string } | null>(null);
    const [refresh, setRefresh] = useState({ key: "", version: 0 });
    const [result, setResult] = useState<Result | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const normalizedFilters = {
        q: filters.q, tag_id: filters.tagId || null, date_from: filters.from || null, date_to: filters.to || null,
        free_only: filters.freeOnly, available_only: filters.availableOnly,
        friends_of: filters.withFriends ? userId : null, viewer_id: userId,
    };
    const scope = JSON.stringify(normalizedFilters);
    const [previousScope, setPreviousScope] = useState(scope);
    if (previousScope !== scope) {
        setPreviousScope(scope);
        setSelection(null);
        setPage(null);
        setNotice(null);
        setSortNotice(null);
    }
    const selected = !mapCollapsed && selection?.scope === scope ? selection.item : null;
    const activeViewport = mapCollapsed ? null : viewport;
    const distanceOrigin = mapCollapsed && viewport ? viewport.center : origin;
    const base = { filters: normalizedFilters, viewport: activeViewport, sort,
        origin: sort === "distance" && !activeViewport ? distanceOrigin : null,
        selection_token: selected?.selection_token ?? null };
    const key = JSON.stringify(base);
    const cursor = page?.key === key ? page.cursor : null;
    const body: DiscoveryRequest = { ...base, cursor, limit: 20, include_map: !cursor && !mapCollapsed };
    const version = refresh.key === key ? refresh.version : 0;
    const requestKey = JSON.stringify(body) + `:${version}`;
    const resolvedRequestKey = result?.requestKey;

    useEffect(() => {
        if (!isFeedRoute || userLoading || resolvedRequestKey === requestKey) return;
        const controller = new AbortController();
        // Parsing the stable key avoids effect restarts due to object/callback identity changes.
        const request = JSON.parse(requestKey.slice(0, requestKey.lastIndexOf(":"))) as DiscoveryRequest;
        discoveryCache.get(request, controller.signal, version > 0).then((response) => {
            if (controller.signal.aborted) return;
            setResult((previous) => ({ key, requestKey, userId,
                events: cursor && previous?.key === key ? mergeDiscoveryEvents(previous.events, response.feed.items) : response.feed.items,
                map: response.map ?? (previous?.userId === userId ? previous.map : null),
                mapViewport: response.map ? request.viewport : previous?.mapViewport ?? null,
                total: response.feed.total_events, next: response.feed.next_cursor,
                refreshAfterSeconds: response.feed.refresh_after_seconds,
            }));
        }, (error: unknown) => {
            if (controller.signal.aborted) return;
            if (error instanceof ApiError && error.status === 409 && (request.selection_token || cursor)) {
                discoveryCache.clear();
                setSelection(null); setPage(null);
                setRefresh((previous) => ({ key, version: previous.version + 1 }));
                setNotice("Данные выбранной области обновились. Выдача загружена заново.");
                return;
            }
            setResult((previous) => ({ key, requestKey, userId,
                events: previous?.userId === userId ? previous.events : [],
                map: previous?.userId === userId ? previous.map : null,
                mapViewport: previous?.userId === userId ? previous.mapViewport : null,
                total: previous?.key === key ? previous.total : undefined, next: null, error,
            }));
        });
        return () => controller.abort();
    }, [requestKey, key, userId, userLoading, cursor, version, isFeedRoute, resolvedRequestKey]);

    const visible = result?.userId === userId ? result : null;
    const loading = userLoading || resolvedRequestKey !== requestKey;
    const next = !loading && visible?.key === key ? visible.next : null;
    const refreshAfterSeconds = visible?.refreshAfterSeconds;
    useEffect(() => {
        if (!next || !refreshAfterSeconds) return;
        const controller = new AbortController();
        const interval = refreshAfterSeconds * 1000;
        let timer: number;
        let retry = true;
        const schedule = (delay: number) => {
            timer = window.setTimeout(async () => {
                try {
                    const { next_cursor } = await refreshDiscoverySession(next, controller.signal);
                    if (controller.signal.aborted) return;
                    if (next_cursor === next) {
                        retry = true;
                        schedule(interval);
                        return;
                    }
                    setResult((previous) => previous?.requestKey === requestKey && previous.next === next
                        ? { ...previous, next: next_cursor } : previous);
                } catch (error) {
                    if (controller.signal.aborted || (error instanceof ApiError && [401, 403, 409].includes(error.status))) return;
                    schedule(retry ? Math.min(30_000, interval) : interval);
                    retry = false;
                }
            }, delay);
        };
        schedule(interval);
        return () => { controller.abort(); window.clearTimeout(timer); };
    }, [next, refreshAfterSeconds, requestKey]);
    const reload = () => {
        discoveryCache.clear(); setPage(null);
        setRefresh((previous) => ({ key, version: previous.version + 1 }));
    };
    const chooseSort = async (value: DiscoverySort) => {
        const request = ++sortRequest.current;
        const actorId = userId;
        setSortNotice(null);
        const apply = () => { changeSort({ actorId, value }); setPage(null); };
        if (value !== "distance" || viewport || selected) { apply(); return; }
        setSortNotice("Определяем местоположение…");
        try {
            const [longitude, latitude] = await currentCoordinates();
            if (request !== sortRequest.current || actor.current !== actorId) return;
            setPoint({ actorId, longitude, latitude });
            apply();
            setSortNotice(null);
        } catch (failure) {
            if (request !== sortRequest.current || actor.current !== actorId) return;
            if (user?.city) {
                setPoint(null);
                apply();
                setSortNotice(`${errorText(failure)} Используем город из профиля.`);
            } else {
                setSortNotice(errorText(failure));
            }
        }
    };
    return {
        initialFilters: userLoading ? null : normalizedFilters,
        ...filterState, userId, user, viewport, mapCollapsed, sort, selected, notice, sortNotice,
        events: visible?.events, map: visible?.map, total: visible?.key === key ? visible.total : undefined,
        mapViewport: visible?.mapViewport ?? null,
        error: visible?.error, loading, canLoadMore: Boolean(next),
        setViewport: (value: DiscoveryViewport) => {
            if (JSON.stringify(value) === JSON.stringify(viewport)) return;
            setViewport(value); setPage(null);
        },
        setMapCollapsed: (value: boolean) => {
            if (value === mapCollapsed) return;
            sortRequest.current++;
            setMapCollapsed(value); setSelection(null); setPage(null); setNotice(null); setSortNotice(null);
        },
        setSort: chooseSort,
        selectCluster: (item: DiscoveryMapItem) => { setSelection({ scope, item }); setPage(null); setNotice(null); },
        clearSelection: () => { setSelection(null); setPage(null); },
        mapUnavailable: () => {
            if (viewport !== null) { setViewport(null); setSelection(null); setPage(null); }
            if (sort === "distance" && !origin && !user?.city) changeSort(null);
        },
        loadMore: () => { if (next) setPage({ key, cursor: next }); },
        reload,
        onPersonalChange: () => reload(),
    };
}

export type EventDiscoveryController = ReturnType<typeof useEventDiscovery>;
