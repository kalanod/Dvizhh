import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

export interface FeedFilters {
    q: string;
    tagId: string;
    from: string;
    to: string;
    freeOnly: boolean;
    availableOnly: boolean;
    withFriends: boolean;
}

const PARAM_BY_FILTER: Record<keyof FeedFilters, string> = {
    q: "q",
    tagId: "tag_id",
    from: "from",
    to: "to",
    freeOnly: "free",
    availableOnly: "available",
    withFriends: "friends",
};

/** Фильтры ленты хранятся в URL, как в шаблоне: ссылкой с фильтрами можно поделиться. */
export const useEventFilters = (active: boolean) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const routeSearch = searchParams.toString();
    const [lastFeedSearch, setLastFeedSearch] = useState(routeSearch);
    if (active && routeSearch !== lastFeedSearch) setLastFeedSearch(routeSearch);
    const feedSearch = active ? routeSearch : lastFeedSearch;

    const filters = useMemo<FeedFilters>(
        () => {
            const params = new URLSearchParams(feedSearch);
            return {
                q: params.get("q") ?? "",
                tagId: params.get("tag_id") ?? "",
                from: params.get("from") ?? "",
                to: params.get("to") ?? "",
                freeOnly: params.get("free") === "1",
                availableOnly: params.get("available") === "1",
                withFriends: params.get("friends") === "1",
            };
        },
        [feedSearch],
    );

    const setFilters = (patch: Partial<FeedFilters>) => {
        const next = new URLSearchParams(searchParams);
        for (const [key, value] of Object.entries(patch) as [keyof FeedFilters, string | boolean][]) {
            const param = PARAM_BY_FILTER[key];
            if (value === "" || value === false) {
                next.delete(param);
            } else {
                next.set(param, value === true ? "1" : value);
            }
        }
        setSearchParams(next, { replace: true });
    };

    const clearFilters = () => setSearchParams({}, { replace: true });

    const activeCount = [
        filters.tagId,
        filters.from,
        filters.to,
        filters.freeOnly,
        filters.availableOnly,
        filters.withFriends,
    ].filter(Boolean).length;

    return { filters, setFilters, clearFilters, activeCount };
};
