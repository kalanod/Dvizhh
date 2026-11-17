import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError, errorText } from "../api/client";
import type { DiscoveryMapItem, DiscoveryRequest, DiscoveryResponse, DiscoverySort, DiscoveryViewport } from "../api/discovery";
import type { DvizhEvent } from "../models";
import { discoveryCache, mergeDiscoveryEvents } from "../utils/discovery";
import { currentCoordinates } from "../utils/geolocation";
import { locationCoordinates } from "../utils/yandexMaps";
import { useCurrentUser } from "./useCurrentUser";
import { useEventFilters } from "./useEventFilters";

interface Result {
    key: string; requestKey: string; userId: string | null;
    events: DvizhEvent[]; map: DiscoveryResponse["map"]; total: number; next: string | null;
    error?: unknown;
}

/** One owner for the map, filters, selected region and feed pagination. */
export function useEventDiscovery() {
    const { userId, user, loading: userLoading } = useCurrentUser();
    const filterState = useEventFilters();
    const { filters } = filterState;
    const [viewport, setViewport] = useState<DiscoveryViewport | null>(null);
    const [sortChoice, changeSort] = useState<{ actorId: string | null; value: DiscoverySort } | null>(null);
    const [point, setPoint] = useState<{ actorId: string | null; latitude: number; longitude: number } | null>(null);
    const [sortNotice, setSortNotice] = useState<string | null>(null);
    const sortRequest = useRef(0);
    const actor = useRef(userId);
    useLayoutEffect(() => { actor.current = userId; sortRequest.current++; }, [userId]);
    useEffect(() => () => { sortRequest.current++; }, []);
    const sort = sortChoice?.actorId === userId ? sortChoice.value : userId ? "relevance" : "novelty";
    const coordinates = locationCoordinates(user?.latitude ?? "", user?.longitude ?? "");
    const profileOrigin = coordinates ? { longitude: coordinates[0], latitude: coordinates[1] } : null;
    const origin = point?.actorId === userId ? { latitude: point.latitude, longitude: point.longitude } : profileOrigin;
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
    const selected = selection?.scope === scope ? selection.item : null;
    const base = { filters: normalizedFilters, viewport, sort,
        origin: sort === "distance" && !viewport ? origin : null,
        selection_token: selected?.selection_token ?? null };
    const key = JSON.stringify(base);
    const cursor = page?.key === key ? page.cursor : null;
    const body: DiscoveryRequest = { ...base, cursor, limit: 20, include_map: !cursor };
    const version = refresh.key === key ? refresh.version : 0;
    const requestKey = JSON.stringify(body) + `:${version}`;

    useEffect(() => {
        if (userLoading) return;
        const controller = new AbortController();
        // Parsing the stable key avoids effect restarts due to object/callback identity changes.
        const request = JSON.parse(requestKey.slice(0, requestKey.lastIndexOf(":"))) as DiscoveryRequest;
        discoveryCache.get(request, controller.signal, version > 0).then((response) => {
            if (controller.signal.aborted) return;
            setResult((previous) => ({ key, requestKey, userId,
                events: cursor && previous?.key === key ? mergeDiscoveryEvents(previous.events, response.feed.items) : response.feed.items,
                map: response.map ?? (previous?.key === key ? previous.map : null),
                total: response.feed.total_events, next: response.feed.next_cursor,
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
                total: previous?.total ?? 0, next: null, error,
            }));
        });
        return () => controller.abort();
    }, [requestKey, key, userId, userLoading, cursor, version]);

    const visible = result?.userId === userId ? result : null;
    const loading = userLoading || result?.requestKey !== requestKey;
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
            if (profileOrigin) {
                setPoint({ actorId, ...profileOrigin });
                apply();
                setSortNotice(`${errorText(failure)} Показываем события рядом с точкой из профиля.`);
            } else {
                setSortNotice(errorText(failure));
            }
        }
    };
    return {
        ...filterState, userId, user, viewport, sort, selected, notice, sortNotice,
        events: visible?.events, map: visible?.map, total: visible?.total ?? 0,
        error: visible?.error, loading, canLoadMore: result?.key === key && Boolean(result.next) && !loading,
        setViewport: (value: DiscoveryViewport) => { setViewport(value); setPage(null); },
        setSort: chooseSort,
        selectCluster: (item: DiscoveryMapItem) => { setSelection({ scope, item }); setPage(null); setNotice(null); },
        clearSelection: () => { setSelection(null); setPage(null); },
        mapUnavailable: () => {
            setViewport(null); setSelection(null); setPage(null);
            if (sort === "distance" && !origin) changeSort(null);
        },
        loadMore: () => { if (result?.key === key && result.next && !loading) setPage({ key, cursor: result.next }); },
        reload,
        onPersonalChange: () => reload(),
    };
}

export type EventDiscoveryController = ReturnType<typeof useEventDiscovery>;
