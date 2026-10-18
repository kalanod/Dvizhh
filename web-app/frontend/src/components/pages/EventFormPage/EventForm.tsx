import type { ReactNode } from "react";
import { useState } from "react";
import { errorText } from "../../../api";
import type { EventFormat, EventInput, EventJoinPolicy, EventVisibility } from "../../../models";
import { Button, FormField, Input, Notice, Select, Textarea, Toggle } from "../../ui";
import { FORMAT_LABELS, JOIN_POLICY_LABELS, VISIBILITY_LABELS } from "../../../utils/format";
import { emptyForm, formToInput, validateForm, type EventFormState } from "./formState";

interface EventFormProps {
    title: string;
    submitLabel: string;
    initial?: EventFormState;
    onSubmit: (input: EventInput) => Promise<void>;
    onCancel: () => void;
}

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
    <fieldset className="flex flex-col gap-4 rounded-2xl border border-bordersoft p-5">
        <legend className="px-2 text-h3 text-textprimary">{title}</legend>
        {children}
    </fieldset>
);

export const EventForm = ({ title, submitLabel, initial, onSubmit, onCancel }: EventFormProps) => {
    const [form, setForm] = useState<EventFormState>(() => initial ?? emptyForm());
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const set =
        <K extends keyof EventFormState>(key: K) =>
        (value: EventFormState[K]) =>
            setForm((prev) => ({ ...prev, [key]: value }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        const problem = validateForm(form);
        if (problem) {
            setError(problem);
            return;
        }
        setSubmitting(true);
        setError(null);
        try {
            await onSubmit(formToInput(form));
        } catch (err) {
            setError(errorText(err));
            setSubmitting(false);
        }
    };

    return (
        <form
            onSubmit={handleSubmit}
            noValidate
            className="mx-auto flex w-full max-w-[820px] flex-col gap-5 rounded-2xl bg-cards-surface p-6 shadow-card sm:p-8"
        >
            <div className="flex flex-col gap-1">
                <h1 className="text-h1 text-textprimary">{title}</h1>
                <p className="text-body text-textsecondary">
                    Любой формат подойдёт: от концерта до «ищем четвёртого в теннис».
                </p>
            </div>

            <Section title="Что за движ">
                <FormField label="Название" htmlFor="title" required>
                    <Input id="title" maxLength={200} placeholder="Поход в Выборг" value={form.title} onChange={set("title")} />
                </FormField>
                <FormField label="Описание" htmlFor="description">
                    <Textarea
                        id="description"
                        rows={5}
                        placeholder="Что будет, что взять с собой, кого ждём"
                        value={form.description}
                        onChange={set("description")}
                    />
                </FormField>
                <FormField label="Тематики" htmlFor="tags" hint="Через запятую: походы, природа, выходные">
                    <Input id="tags" placeholder="походы, природа" value={form.tags} onChange={set("tags")} />
                </FormField>
            </Section>

            <Section title="Когда">
                <div className="grid gap-4 sm:grid-cols-2">
                    <FormField label="Начало" htmlFor="starts-at" required>
                        <Input id="starts-at" type="datetime-local" value={form.startsAt} onChange={set("startsAt")} />
                    </FormField>
                    <FormField label="Окончание" htmlFor="ends-at">
                        <Input
                            id="ends-at"
                            type="datetime-local"
                            min={form.startsAt || undefined}
                            value={form.endsAt}
                            onChange={set("endsAt")}
                        />
                    </FormField>
                </div>
                <Toggle label="Весь день" checked={form.isAllDay} onChange={set("isAllDay")} />
                <span className="text-small font-medium text-textsecondary">Часовой пояс: {form.timezone}</span>
            </Section>

            <Section title="Где">
                <FormField label="Формат" htmlFor="format">
                    <Select<EventFormat> id="format" value={form.format} options={FORMAT_LABELS} onChange={set("format")} />
                </FormField>

                {form.format !== "ONLINE" && (
                    <>
                        <div className="grid gap-4 sm:grid-cols-2">
                            <FormField label="Место" htmlFor="place-name">
                                <Input id="place-name" maxLength={200} placeholder="Антикафе «Ход конём»" value={form.placeName} onChange={set("placeName")} />
                            </FormField>
                            <FormField label="Город" htmlFor="city">
                                <Input id="city" maxLength={120} placeholder="Санкт-Петербург" value={form.city} onChange={set("city")} />
                            </FormField>
                        </div>
                        <FormField label="Адрес" htmlFor="address">
                            <Input id="address" placeholder="Невский пр., 1" value={form.address} onChange={set("address")} />
                        </FormField>
                        <div className="grid gap-4 sm:grid-cols-2">
                            <FormField label="Широта" htmlFor="latitude" required>
                                <Input id="latitude" inputMode="decimal" value={form.latitude} onChange={set("latitude")} />
                            </FormField>
                            <FormField label="Долгота" htmlFor="longitude" required>
                                <Input id="longitude" inputMode="decimal" value={form.longitude} onChange={set("longitude")} />
                            </FormField>
                        </div>
                    </>
                )}

                {form.format !== "OFFLINE" && (
                    <FormField label="Ссылка на трансляцию" htmlFor="online-url" required>
                        <Input id="online-url" type="url" placeholder="https://" value={form.onlineUrl} onChange={set("onlineUrl")} />
                    </FormField>
                )}
            </Section>

            <Section title="Участие">
                <div className="grid gap-4 sm:grid-cols-3">
                    <FormField label="Цена от, ₽" htmlFor="price-min" hint="Пусто или 0 — бесплатно">
                        <Input id="price-min" type="number" min={0} inputMode="decimal" value={form.priceMin} onChange={set("priceMin")} />
                    </FormField>
                    <FormField label="Цена до, ₽" htmlFor="price-max">
                        <Input
                            id="price-max"
                            type="number"
                            min={0}
                            inputMode="decimal"
                            disabled={!form.priceMin}
                            value={form.priceMax}
                            onChange={set("priceMax")}
                        />
                    </FormField>
                    <FormField label="Мест" htmlFor="capacity" hint="Пусто — без лимита">
                        <Input id="capacity" type="number" min={1} inputMode="numeric" value={form.capacity} onChange={set("capacity")} />
                    </FormField>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                    <FormField label="Как попасть" htmlFor="join-policy">
                        <Select<EventJoinPolicy>
                            id="join-policy"
                            value={form.joinPolicy}
                            options={JOIN_POLICY_LABELS}
                            onChange={set("joinPolicy")}
                        />
                    </FormField>
                    <FormField label="Кто видит" htmlFor="visibility">
                        <Select<EventVisibility>
                            id="visibility"
                            value={form.visibility}
                            options={VISIBILITY_LABELS}
                            onChange={set("visibility")}
                        />
                    </FormField>
                </div>
                <FormField label="Внешняя регистрация или билеты" htmlFor="registration-url">
                    <Input
                        id="registration-url"
                        type="url"
                        placeholder="https://"
                        value={form.registrationUrl}
                        onChange={set("registrationUrl")}
                    />
                </FormField>
            </Section>

            {error && <Notice tone="error">{error}</Notice>}

            <div className="flex flex-wrap justify-end gap-2">
                <Button state="outline" onClick={onCancel}>
                    Отмена
                </Button>
                <Button type="submit" state="hover1" disabled={submitting}>
                    {submitting ? "Сохраняем…" : submitLabel}
                </Button>
            </div>
        </form>
    );
};
