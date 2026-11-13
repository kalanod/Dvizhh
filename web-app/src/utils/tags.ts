import type { EventTag } from "../models/tag";

export const MAX_EVENT_TAGS = 5;

export const toggleEventTag = (selected: EventTag[], tag: EventTag): EventTag[] => {
    if (selected.some((item) => item.id === tag.id)) return selected.filter((item) => item.id !== tag.id);
    if (!tag.is_active || selected.length >= MAX_EVENT_TAGS) return selected;
    return [...selected, tag];
};

export const tagColorStyle = (color: string) => {
    const safeColor = /^#[0-9a-f]{6}$/i.test(color) ? color : "#64748b";
    return { backgroundColor: `${safeColor}20`, borderColor: safeColor };
};
