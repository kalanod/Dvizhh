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
    <aside className="flex h-fit w-full flex-col gap-[10px] lg:sticky lg:top-6 lg:w-[320px] lg:shrink-0">
        {children}

        <div className="flex flex-col gap-[10px] rounded-2xl bg-background/90 p-[14px] shadow-card">
            <div className="flex items-center justify-between px-1">
                <h2 className="text-h2 text-textthird">Фильтры</h2>
                {activeCount > 0 && (
                    <button
                        type="button"
                        onClick={onClear}
                        className="cursor-pointer text-small text-textmuted transition hover:text-textthird"
                    >
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

            <AccordionFilter title="Тематика" activeCount={Number(Boolean(filters.tag))} defaultOpen>
                <Input
                    placeholder="Например, настолки"
                    aria-label="Тематика"
                    value={filters.tag}
                    onChange={(tag) => onChange({ tag: tag.toLowerCase() })}
                />
                {suggestedTags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                        {suggestedTags.map((tag) => (
                            <Tag
                                key={tag}
                                label={tag}
                                variant={filters.tag === tag ? "price" : "topic"}
                                onClick={() => onChange({ tag: filters.tag === tag ? "" : tag })}
                            />
                        ))}
                    </div>
                )}
            </AccordionFilter>

            <AccordionFilter
                title="Параметры"
                activeCount={[filters.freeOnly, filters.availableOnly, filters.withFriends].filter(Boolean).length}
                defaultOpen
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
        </div>
    </aside>
);
