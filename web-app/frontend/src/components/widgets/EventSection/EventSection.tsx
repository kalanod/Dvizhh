import { useMemo, useState } from "react";
import { listEvents, errorText } from "../../../api";
import { useAsync, useCurrentUser, useEventFilters } from "../../../hooks";
import { Button, Input, Tag } from "../../ui";
import { CalendarPreview } from "../CalendarPreview";
import { EventList } from "../EventList";
import { RightPanel } from "../Filters";

const PAGE_SIZE = 20;
const MAX_LIMIT = 100;

type SortMode = "for-you" | "newest";

/** Лента событий: поиск, сортировка, список и панель фильтров (аналог BookSection шаблона). */
export const EventSection = () => {
    const { userId } = useCurrentUser();
    const { filters, setFilters, clearFilters, activeCount } = useEventFilters();
    const [searchValue, setSearchValue] = useState(filters.q);
    const [sort] = useState<SortMode>("newest");
    const [limit, setLimit] = useState(PAGE_SIZE);

    const query = {
        q: filters.q,
        tag: filters.tag,
        from: filters.from,
        to: filters.to,
        freeOnly: filters.freeOnly,
        availableOnly: filters.availableOnly,
        friendsOf: filters.withFriends && userId ? userId : undefined,
        limit,
    };
    const { data: events, error, loading } = useAsync(() => listEvents(query), JSON.stringify(query));

    const suggestedTags = useMemo(() => {
        const counts = new Map<string, number>();
        for (const event of events ?? []) {
            for (const tag of event.tags) {
                counts.set(tag, (counts.get(tag) ?? 0) + 1);
            }
        }
        return [...counts.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 12)
            .map(([tag]) => tag);
    }, [events]);

    const applyFilters = (patch: Parameters<typeof setFilters>[0]) => {
        setLimit(PAGE_SIZE);
        setFilters(patch);
    };

    const handleSearch = () => applyFilters({ q: searchValue.trim() });

    const handleClearAll = () => {
        setSearchValue("");
        setLimit(PAGE_SIZE);
        clearFilters();
    };

    const activeChips = [
        filters.q && `«${filters.q}»`,
        filters.tag && `#${filters.tag}`,
        filters.from && `с ${new Date(filters.from).toLocaleDateString("ru-RU")}`,
        filters.to && `по ${new Date(filters.to).toLocaleDateString("ru-RU")}`,
        filters.freeOnly && "бесплатные",
        filters.availableOnly && "есть места",
        filters.withFriends && userId && "друзья идут",
    ].filter((chip): chip is string => Boolean(chip));

    const hasMore =(events?.length ?? 0) >= limit && limit < MAX_LIMIT;

    const searchBar = (
        <>
            <div className="flex w-full gap-2">
                <form
                    className="flex min-w-0 flex-1 gap-2"
                    onSubmit={(e) => {
                        e.preventDefault();
                        handleSearch();
                    }}
                    role="search"
                >
                    <Input
                        type="search"
                        placeholder="Найти движ: концерт, поход, настолки…"
                        aria-label="Поиск событий"
                        value={searchValue}
                        onChange={setSearchValue}
                        className="min-w-0 flex-1"
                    />
                    <button
                        type="submit"
                        className="inline-flex h-[41px] w-[41px] shrink-0 cursor-pointer items-center justify-center rounded-xl bg-primary text-textprimary transition-all hover:bg-surface-muted"
                        aria-label="Искать"
                    >
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path
                                d="M15.5 15.5L19 19M17 10C17 13.866 13.866 17 10 17C6.13401 17 3 13.866 3 10C3 6.13401 6.13401 3 10 3C13.866 3 17 6.13401 17 10Z"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                            />
                        </svg>
                    </button>
                </form>
            </div>
            <div className="flex flex-wrap items-center gap-2">
                <Button state="disabled" title="Персональная выдача появится вместе с рекомендательным сервисом">
                    Для тебя · скоро
                </Button>
                <Button state={sort === "newest" ? "fixed2" : "ghost"} ariaPressed={sort === "newest"}>
                    По новизне
                </Button>
            </div>
        </>
    );

    return (
        <section className="flex w-full flex-col-reverse gap-[12px] lg:flex-row lg:items-start">
            <div className="flex min-w-0 flex-1 flex-col gap-[12px]">
                {activeChips.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 rounded-2xl bg-cards-surface px-4 py-3">
                        <span className="text-small text-textsecondary">Активные фильтры:</span>
                        {activeChips.map((chip) => (
                            <Tag key={chip} label={chip} variant="muted" />
                        ))}
                        <button
                            type="button"
                            onClick={handleClearAll}
                            className="ml-auto cursor-pointer rounded-lg border border-bordersoft px-3 py-1 text-small text-textsecondary transition hover:text-bordermain"
                        >
                            Сбросить все
                        </button>
                    </div>
                )}

                <EventList
                    title="Афиша"
                    actionButton={searchBar}
                    events={events}
                    loading={loading}
                    error={error ? errorText(error) : null}
                    emptyText={
                        filters.q || activeCount > 0
                            ? "Под эти фильтры ничего не нашлось. Попробуйте ослабить условия."
                            : "В ленте пока пусто — создайте первый движ!"
                    }
                    onTagClick={(tag) => applyFilters({ tag })}
                    footer={
                        hasMore && !loading ? (
                            <Button state="ghost" className="self-center" onClick={() => setLimit((value) => Math.min(value + PAGE_SIZE, MAX_LIMIT))}>
                                Показать ещё
                            </Button>
                        ) : null
                    }
                />
            </div>

            <RightPanel
                filters={filters}
                activeCount={activeCount}
                onChange={applyFilters}
                onClear={handleClearAll}
                suggestedTags={suggestedTags}
                canFilterByFriends={Boolean(userId)}
            >
                {userId && <CalendarPreview userId={userId} />}
            </RightPanel>
        </section>
    );
};
