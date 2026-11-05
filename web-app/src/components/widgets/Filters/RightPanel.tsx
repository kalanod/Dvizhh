import type { ReactNode } from "react";
import { AccordionFilter } from "./AccordionFilter";
import { FormField, Input, Tag, Toggle } from "../../ui";
import type { FeedFilters } from "../../../hooks";

interface RightPanelProps {
    filters: FeedFilters;
    activeCount: number;
    onChange: (patch: Partial<FeedFilters>) => void;
    onClear: () => void;
    /** Тематики, встречающиеся в текущей выдаче — для быстрого выбора. */
    suggestedTags: string[];
    canFilterByFriends: boolean;
    children?: ReactNode;
}

export const RightPanel = ({
    filters,
    activeCount,
    onChange,
    onClear,
    suggestedTags,
    canFilterByFriends,
    children,
}: RightPanelProps) => (
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

            <AccordionFilter title="Тематики" activeCount={Number(Boolean(filters.tag))}>
                <Input
                    placeholder="Поиск (Тематики)..."
                    aria-label="Тематика"
                    value={filters.tag}
                    onChange={(tag) => onChange({ tag: tag.toLowerCase() })}
                />
                {suggestedTags.length > 0 ? (
                    <div className="flex max-h-[300px] flex-wrap gap-2 overflow-y-auto">
                        {suggestedTags.map((tag) => (
                            <Tag
                                key={tag}
                                label={tag}
                                variant={filters.tag === tag ? "free" : "topic"}
                                onClick={() => onChange({ tag: filters.tag === tag ? "" : tag })}
                            />
                        ))}
                    </div>
                ) : (
                    <div className="px-2 py-2 text-center text-sm text-textsecondary">Ничего не найдено</div>
                )}
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
