import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export interface FeedFilters {
    q: string;
    tag: string;
    from: string;
    to: string;
    freeOnly: boolean;
    availableOnly: boolean;
    withFriends: boolean;
}

const PARAM_BY_FILTER: Record<keyof FeedFilters, string> = {
    q: "q",
    tag: "tag",
    from: "from",
    to: "to",
    freeOnly: "free",
    availableOnly: "available",
    withFriends: "friends",
};

/** Фильтры ленты хранятся в URL, как в шаблоне: ссылкой с фильтрами можно поделиться. */
export const useEventFilters = () => {
    const [searchParams, setSearchParams] = useSearchParams();

    const filters = useMemo<FeedFilters>(
        () => ({
            q: searchParams.get("q") ?? "",
            tag: searchParams.get("tag") ?? "",
            from: searchParams.get("from") ?? "",
            to: searchParams.get("to") ?? "",
            freeOnly: searchParams.get("free") === "1",
            availableOnly: searchParams.get("available") === "1",
            withFriends: searchParams.get("friends") === "1",
        }),
        [searchParams],
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
        filters.tag,
        filters.from,
        filters.to,
        filters.freeOnly,
        filters.availableOnly,
        filters.withFriends,
    ].filter(Boolean).length;

    return { filters, setFilters, clearFilters, activeCount };
};
