import { useState } from "react";
import { errorText } from "../../../api";
import type { EventDiscoveryController } from "../../../hooks/useEventDiscovery";
import { Button, Input, Notice, Tag } from "../../ui";
import { CalendarPreview } from "../CalendarPreview";
import { EventList } from "../EventList";
import { RightPanel } from "../Filters";
import { SortMenu } from "../SortMenu";
import { discoveryEmptyText } from "../../../utils/discovery";

interface EventSectionProps {
    title: string;
    discovery: EventDiscoveryController;
}

/** Лента событий: поиск, список и панель фильтров (BookSection шаблона). */
export const EventSection = ({ title, discovery }: EventSectionProps) => {
    const { userId, filters, setFilters, clearFilters, activeCount, events, error, loading } = discovery;
    const [searchValue, setSearchValue] = useState(filters.q);
    const applyFilters = (patch: Parameters<typeof setFilters>[0]) => setFilters(patch);

    const handleSearch = () => applyFilters({ q: searchValue.trim() });

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
            handleSearch();
        }
    };

    const handleClearAllFilters = () => {
        setSearchValue("");
        discovery.clearSelection();
        clearFilters();
    };

    const activeChips = [
        filters.q && `«${filters.q}»`,
        filters.tagId && (events?.flatMap((event) => event.tags).find((tag) => tag.id === filters.tagId)?.name ?? "Фильтр по тематике"),
        filters.from && `с ${new Date(filters.from).toLocaleDateString("ru-RU")}`,
        filters.to && `по ${new Date(filters.to).toLocaleDateString("ru-RU")}`,
        filters.freeOnly && "бесплатные",
        filters.availableOnly && "есть места",
        filters.withFriends && userId && "друзья идут",
    ].filter((chip): chip is string => Boolean(chip));

    const hasMore = discovery.canLoadMore;

    const searchButton = (
        <>
            <button
                onClick={handleSearch}
                type="button"
                className="inline-flex h-[41px] w-[41px] shrink-0 cursor-pointer items-center justify-center rounded-lg bg-primary transition-all hover:bg-borderlight"
                aria-label="Поиск"
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
            <div className="min-w-0 flex-1">
                <Input
                    placeholder="Поиск событий..."
                    aria-label="Поиск событий"
                    value={searchValue}
                    onChange={setSearchValue}
                    onKeyDown={handleKeyDown}
                />
            </div>
            <SortMenu value={discovery.sort} onChange={(value) => void discovery.setSort(value)}
                distanceLabel={discovery.viewport ? "Ближе к центру карты" : "Рядом со мной"} />
        </>
    );

    return (
        <section className="flex w-full flex-col gap-[10px] lg:flex-row lg:items-start">
            <div className="flex min-w-0 flex-1 flex-col gap-[10px]">
                {discovery.selected && <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-cards-surface p-3" role="status">
                    <span className="text-body text-textprimary">Выбрана группа: {discovery.total} мероприятий</span>
                    <Button onClick={discovery.clearSelection}>Сбросить выбор группы</Button>
                </div>}
                {discovery.notice && <p role="status" className="text-small text-textsecondary">{discovery.notice}</p>}
                {activeChips.length > 0 && (
                    <div className="flex flex-wrap items-center gap-2 rounded-lg bg-cards-surface px-4 py-3">
                        <span className="text-small font-medium text-textsecondary">Активные фильтры:</span>
                        {activeChips.map((chip) => (
                            <Tag key={chip} label={chip} variant="muted" />
                        ))}
                        <button
                            onClick={handleClearAllFilters}
                            className="ml-auto cursor-pointer rounded-lg border border-borderlight px-3 py-1 text-small text-textsecondary transition hover:text-primary"
                        >
                            Сбросить все
                        </button>
                    </div>
                )}

                {discovery.sortNotice && <Notice>{discovery.sortNotice}</Notice>}

                <EventList
                    title={title}
                    events={events}
                    actionButton={searchButton}
                    loading={loading}
                    error={error ? errorText(error) : null}
                    emptyText={discoveryEmptyText(
                        !discovery.mapCollapsed && discovery.viewport !== null,
                        Boolean(discovery.selected), activeChips.length > 0,
                    )}
                    onTagClick={(tagId) => applyFilters({ tagId })}
                    collapseDismissed
                    onPersonalChange={discovery.onPersonalChange}
                    footer={
                        hasMore && !loading ? (
                            <Button
                                state="hover1"
                                className="self-center"
                                onClick={discovery.loadMore}
                            >
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
                onClear={handleClearAllFilters}
                canFilterByFriends={Boolean(userId)}
            >
                {/* На телефоне и планшете превью календаря скрыто: оно отодвигало бы ленту, а календарь есть в меню. */}
                {userId && (
                    <div className="hidden lg:block">
                        <CalendarPreview userId={userId} />
                    </div>
                )}
            </RightPanel>
        </section>
    );
};
