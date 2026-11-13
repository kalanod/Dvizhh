import { listTags, errorText } from "../../../api";
import { useAsync } from "../../../hooks";
import type { EventTag } from "../../../models";
import { MAX_EVENT_TAGS, tagColorStyle, toggleEventTag } from "../../../utils/tags";
import { Button, Notice } from "../../ui";

interface Props {
    selected: EventTag[];
    initialTags?: EventTag[];
    disabled: boolean;
    onChange: (tags: EventTag[]) => void;
}

export const EventTagField = ({ selected, initialTags = [], disabled, onChange }: Props) => {
    const catalog = useAsync(listTags, "tag-catalog");
    const availableIds = new Set(catalog.data?.flatMap((category) => category.tags.map((tag) => tag.id)));
    const unavailable = initialTags.filter((tag) => !tag.is_active || (catalog.data && !availableIds.has(tag.id)));
    const atLimit = selected.length >= MAX_EVENT_TAGS;

    const tile = (tag: EventTag, unavailable = false) => {
        const checked = selected.some((item) => item.id === tag.id);
        const locked = disabled || (!checked && (atLimit || unavailable));
        return (
            <label key={tag.id} className={`relative max-w-full ${locked ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}>
                <input
                    type="checkbox"
                    className="peer sr-only"
                    checked={checked}
                    disabled={locked}
                    onChange={() => onChange(toggleEventTag(selected, tag))}
                />
                <span
                    className={`flex min-h-11 items-center gap-2 rounded-lg border-2 px-3 py-2 text-body text-textprimary transition peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-textprimary ${checked ? "ring-2 ring-textprimary" : "hover:opacity-80"}`}
                    style={tagColorStyle(tag.category.color)}
                >
                    <span aria-hidden="true" className="w-4 shrink-0 text-center">{checked ? "✓" : "+"}</span>
                    <span className="break-words">{tag.name}{unavailable ? " · отключён" : ""}</span>
                </span>
            </label>
        );
    };

    return (
        <fieldset className="flex min-w-0 flex-col gap-3">
            <legend className="text-body text-textprimary">Теги</legend>
            <p className="text-small text-textsecondary" role="status" aria-live="polite">
                Выбрано {selected.length} / {MAX_EVENT_TAGS}. {atLimit ? "Снимите тег, чтобы выбрать другой." : "Можно выбрать до пяти тегов или оставить без тегов."}
            </p>
            {catalog.loading && <p role="status" className="text-small text-textsecondary">Загружаем теги…</p>}
            {catalog.error != null && (
                <div className="flex flex-col items-start gap-2">
                    <Notice tone="error">{errorText(catalog.error)}</Notice>
                    <Button onClick={catalog.reload} disabled={disabled}>Повторить загрузку тегов</Button>
                </div>
            )}
            {!catalog.data && initialTags.length > 0 && (
                <div className="flex flex-wrap gap-2">
                    {initialTags.filter((tag) => tag.is_active).map((tag) => tile(tag))}
                </div>
            )}
            {catalog.data?.map((category) => (
                <fieldset key={category.id} className="flex min-w-0 flex-col gap-2">
                    <legend className="mb-2 text-small font-medium text-textsecondary">{category.name}</legend>
                    <div className="flex flex-wrap gap-2">
                        {category.tags.map((tag) => tile({ ...tag, category }))}
                    </div>
                </fieldset>
            ))}
            {catalog.data && !catalog.data.some((category) => category.tags.length) && (
                <p className="text-small text-textsecondary">Тегов пока нет. Событие можно сохранить без них.</p>
            )}
            {unavailable.length > 0 && (
                <div className="flex flex-col gap-2">
                    <p className="text-small text-textsecondary">Ранее выбранные отключённые теги можно сохранить или снять.</p>
                    <div className="flex flex-wrap gap-2">{unavailable.map((tag) => tile(tag, true))}</div>
                </div>
            )}
        </fieldset>
    );
};
