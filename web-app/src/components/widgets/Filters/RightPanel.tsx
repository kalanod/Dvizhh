import { useState, type ReactNode } from "react";
import { AccordionFilter } from "./AccordionFilter";
import { Button, FormField, Input, Notice, Toggle } from "../../ui";
import type { FeedFilters } from "../../../hooks";
import { useAsync } from "../../../hooks";
import { errorText, listTags } from "../../../api";
import { tagColorStyle } from "../../../utils/tags";

interface RightPanelProps {
    filters: FeedFilters;
    activeCount: number;
    onChange: (patch: Partial<FeedFilters>) => void;
    onClear: () => void;
    canFilterByFriends: boolean;
    children?: ReactNode;
}

export const RightPanel = ({
    filters,
    activeCount,
    onChange,
    onClear,
    canFilterByFriends,
    children,
}: RightPanelProps) => {
    const catalog = useAsync(listTags, "filter-tag-catalog");
    const [tagSearch, setTagSearch] = useState("");
    const query = tagSearch.trim().toLocaleLowerCase("ru");
    const categories = (catalog.data ?? []).map((category) => ({
        ...category,
        tags: category.tags.filter((tag) => `${category.name} ${tag.name}`.toLocaleLowerCase("ru").includes(query)),
    })).filter((category) => category.tags.length > 0);
    return (
    <div className="flex w-full flex-col gap-[10px] max-lg:order-first lg:w-[300px] lg:shrink-0">
        {children}

        <aside className="flex h-fit w-full flex-col gap-[10px] rounded-lg bg-background p-[10px]">
            <div className="mb-2 flex items-center justify-between px-2">
                <h3 className="text-h3 text-textthird">Фильтры</h3>
                {activeCount > 0 && (
                    <button onClick={onClear} className="cursor-pointer text-small text-textsecondary transition hover:text-primary">
                        Сбросить все
                    </button>
                )}
            </div>

            <AccordionFilter title="Даты" activeCount={Number(Boolean(filters.from)) + Number(Boolean(filters.to))}>
                <FormField label="С" htmlFor="filter-from">
                    <Input id="filter-from" type="date" value={filters.from} onChange={(from) => onChange({ from })} />
                </FormField>
                <FormField label="По" htmlFor="filter-to">
                    <Input id="filter-to" type="date" value={filters.to} min={filters.from || undefined} onChange={(to) => onChange({ to })} />
                </FormField>
            </AccordionFilter>

            <AccordionFilter title="Теги" activeCount={Number(Boolean(filters.tagId))}>
                <Input
                    placeholder="Найти тег…"
                    aria-label="Поиск тегов"
                    value={tagSearch}
                    onChange={setTagSearch}
                />
                {filters.tagId && <Button onClick={() => onChange({ tagId: "" })}>Снять фильтр по тегу</Button>}
                {catalog.loading && <p role="status" className="text-small text-textsecondary">Загружаем теги…</p>}
                {catalog.error != null && (
                    <div className="flex flex-col items-start gap-2">
                        <Notice tone="error">{errorText(catalog.error)}</Notice>
                        <Button onClick={catalog.reload}>Повторить загрузку тегов</Button>
                    </div>
                )}
                <div className="flex max-h-[400px] flex-col gap-3 overflow-y-auto p-1">
                    {categories.map((category) => (
                        <div key={category.id} className="flex flex-col gap-2">
                            <span className="text-small text-textsecondary">{category.name}</span>
                            <div className="flex flex-wrap gap-2">
                                {category.tags.map((tag) => (
                                    <button
                                        key={tag.id}
                                        type="button"
                                        aria-pressed={filters.tagId === tag.id}
                                        onClick={() => onChange({ tagId: filters.tagId === tag.id ? "" : tag.id })}
                                        className={`min-h-9 max-w-full cursor-pointer break-words rounded-lg border px-2 py-1 text-small text-textprimary focus-visible:outline-2 focus-visible:outline-offset-2 ${filters.tagId === tag.id ? "ring-2 ring-textprimary" : "hover:opacity-80"}`}
                                        style={tagColorStyle(category.color)}
                                    >
                                        {filters.tagId === tag.id && <span aria-hidden="true">✓ </span>}{tag.name}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ))}
                    {catalog.data && !categories.length && <p className="text-small text-textsecondary">Теги не найдены</p>}
                </div>
            </AccordionFilter>

            <AccordionFilter
                title="Параметры"
                activeCount={[filters.freeOnly, filters.availableOnly, filters.withFriends].filter(Boolean).length}
            >
                <Toggle label="Только бесплатные" checked={filters.freeOnly} onChange={(freeOnly) => onChange({ freeOnly })} />
                <Toggle
                    label="Есть свободные места"
                    checked={filters.availableOnly}
                    onChange={(availableOnly) => onChange({ availableOnly })}
                />
                <Toggle
                    label="Сначала, куда идут друзья"
                    checked={filters.withFriends && canFilterByFriends}
                    disabled={!canFilterByFriends}
                    hint={canFilterByFriends ? undefined : "Войдите, чтобы видеть события друзей"}
                    onChange={(withFriends) => onChange({ withFriends })}
                />
            </AccordionFilter>
        </aside>
    </div>
    );
};
