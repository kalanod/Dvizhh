import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError, getFeedPage, refreshFeedSession } from "../api";
import type { DvizhEvent, FeedQuery, FeedRanking } from "../models";

/** Сервер хранит сессию 30 минут; продлеваем с запасом. */
const REFRESH_INTERVAL_MS = 10 * 60 * 1000;

export interface FeedCoordinates {
    latitude: number;
    longitude: number;
}

interface FeedOptions {
    /** false — лента не запрашивается (например, включены фильтры). */
    enabled: boolean;
    /** null — сортировку выбирает сервер. */
    ranking: FeedRanking | null;
    viewerId: string | null;
    coordinates: FeedCoordinates | null;
    pageSize: number;
}

interface FeedState {
    key: string;
    items: DvizhEvent[];
    ranking?: FeedRanking;
    sessionId?: string;
    nextPageToken: string | null;
    loadingMore: boolean;
    error?: unknown;
}

/**
 * Лента сервиса рекомендаций с постраничной загрузкой по next_page_token.
 * Смена сортировки, координат или пользователя начинает новую сессию;
 * истёкшая сессия (409) тоже начинается заново. Пока лента открыта,
 * сессия продлевается раз в 10 минут.
 */
export const useFeed = ({ enabled, ranking, viewerId, coordinates, pageSize }: FeedOptions) => {
    const [state, setState] = useState<FeedState | null>(null);
    const [restarts, setRestarts] = useState(0);
    const key = `${JSON.stringify({ ranking, viewerId, coordinates, pageSize })}#${restarts}`;

    const queryRef = useRef<FeedQuery>({});
    useLayoutEffect(() => {
        queryRef.current = {
            ranking: ranking ?? undefined,
            viewerId,
            latitude: coordinates?.latitude,
            longitude: coordinates?.longitude,
            limit: pageSize,
        };
    });

    const moreRef = useRef<AbortController | null>(null);
    const restart = useCallback(() => setRestarts((value) => value + 1), []);

    useEffect(() => {
        if (!enabled) return;
        const controller = new AbortController();
        const { signal } = controller;
        getFeedPage(queryRef.current, signal).then(
            (page) =>
                !signal.aborted &&
                setState({
                    key,
                    items: page.items,
                    ranking: page.ranking,
                    sessionId: page.session_id,
                    nextPageToken: page.next_page_token,
                    loadingMore: false,
                }),
            (error: unknown) =>
                !signal.aborted && setState({ key, items: [], nextPageToken: null, loadingMore: false, error }),
        );
        return () => {
            controller.abort();
            moreRef.current?.abort();
        };
    }, [enabled, key]);

    const current = enabled && state?.key === key ? state : null;

    const loadMore = useCallback(() => {
        if (!current?.sessionId || !current.nextPageToken || current.loadingMore) return;
        const controller = new AbortController();
        moreRef.current = controller;
        setState({ ...current, loadingMore: true, error: undefined });
        const sameFeed = (previous: FeedState | null) => previous?.key === current.key;
        getFeedPage(
            { ...queryRef.current, sessionId: current.sessionId, pageToken: current.nextPageToken },
            controller.signal,
        ).then(
            (page) =>
                setState((previous) =>
                    previous && sameFeed(previous)
                        ? {
                              ...previous,
                              items: [...previous.items, ...page.items],
                              nextPageToken: page.next_page_token,
                              loadingMore: false,
                          }
                        : previous,
                ),
            (error: unknown) => {
                if (controller.signal.aborted) return;
                if (error instanceof ApiError && error.status === 409) {
                    restart();
                    return;
                }
                setState((previous) =>
                    previous && sameFeed(previous) ? { ...previous, loadingMore: false, error } : previous,
                );
            },
        );
    }, [current, restart]);

    const sessionId = current?.sessionId;
    useEffect(() => {
        if (!sessionId) return;
        const timer = window.setInterval(() => {
            // Ошибку не показываем: если сессия всё же истекла, следующая страница начнёт ленту заново.
            refreshFeedSession(sessionId, viewerId).catch(() => undefined);
        }, REFRESH_INTERVAL_MS);
        return () => window.clearInterval(timer);
    }, [sessionId, viewerId]);

    return {
        events: current?.items,
        /** Сортировка, которую применил сервер. */
        ranking: current?.ranking,
        loading: enabled && (current === null || current.loadingMore),
        error: current?.error,
        hasMore: Boolean(current?.nextPageToken),
        loadMore,
        restart,
    };
};
