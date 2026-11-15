import type { ReactNode } from "react";
import { useState } from "react";
import { errorText } from "../../../api";
import type { EventFormat, EventInput, EventJoinPolicy, EventVisibility } from "../../../models";
import { Button, FormField, Input, Notice, Select, Textarea, Toggle } from "../../ui";
import { FORMAT_LABELS, JOIN_POLICY_LABELS, VISIBILITY_LABELS } from "../../../utils/format";
import { emptyForm, formToInput, validateForm, type EventFormState } from "./formState";
import type { EventCoverChange } from "../../../utils/media";
import { EventCoverField } from "./EventCoverField";
import { EventLocationField } from "./EventLocationField";
import { EventTagField } from "./EventTagField";
import { browserTimeZone } from "../../../utils/format";
import { resolveEventTimezone, type EventTimezone } from "../../../api/maps";
import { useAsync, useCurrentUser } from "../../../hooks";
import { placeContextUnchanged, placeCoordinates } from "./eventPlace";

type FormTimezone = Omit<EventTimezone, "source"> & { source: EventTimezone["source"] | "saved"; warning?: string };

interface EventFormProps {
    title: string;
    submitLabel: string;
    initial?: EventFormState;
    allowDraft?: boolean;
    userId: string;
    initialCoverUrl?: string | null;
    onSubmit: (input: EventInput, cover: EventCoverChange, publish: boolean) => Promise<void>;
    onCancel: () => void;
}

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
    <fieldset className="flex min-w-0 flex-col gap-4 rounded-lg border-2 border-borderlight p-3 sm:p-4">
        <legend className="px-2 text-h3 text-textsecondary">{title}</legend>
        {children}
    </fieldset>
);

export const EventForm = ({ title, submitLabel, initial, allowDraft, userId, initialCoverUrl, onSubmit, onCancel }: EventFormProps) => {
    const [form, setForm] = useState<EventFormState>(() => initial ?? emptyForm());
    const [error, setError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const [cover, setCover] = useState<EventCoverChange>({ kind: "keep" });
    const [coverError, setCoverError] = useState<string | null>(null);
    const [locationPending, setLocationPending] = useState(false);
    const [deviceTimezone] = useState(browserTimeZone);
    const { user } = useCurrentUser();
    const keepSavedTimezone = Boolean(initial && placeContextUnchanged(form.place, initial.place));
    const point = form.format === "ONLINE" ? null : placeCoordinates(form.place);
    const timezoneRequest = {
        place: point ? { latitude: point[1], longitude: point[0] } : null,
        user_id: userId, device_timezone: deviceTimezone,
    };
    const timezoneState = useAsync<FormTimezone>(async (signal) => {
        if (initial && keepSavedTimezone) return { timezone: initial.timezone, source: "saved", city: null };
        try { return await resolveEventTimezone(timezoneRequest, signal); }
        catch (failure) {
            if (signal.aborted) throw failure;
            return { timezone: deviceTimezone, source: "device", city: null,
                warning: "Не удалось определить местный часовой пояс. Используется пояс вашего устройства." };
        }
    }, keepSavedTimezone ? `saved-timezone:${initial?.timezone}` : `event-timezone:${JSON.stringify(timezoneRequest)}`);
    const timezone = timezoneState.data?.timezone ?? (keepSavedTimezone ? initial!.timezone : deviceTimezone);
    const timezoneHint = timezoneState.loading ? "Определяем местное время…"
        : timezoneState.data?.source === "saved" ? "Время в часовом поясе сохранённого события."
        : timezoneState.data?.source === "place" ? "Время указано по месту проведения."
        : timezoneState.data?.source === "profile_coordinates" ? "Время указано по местоположению из профиля."
        : timezoneState.data?.source === "profile_city" ? `Время указано по городу профиля${timezoneState.data.city ? ` (${timezoneState.data.city})` : ""}.`
        : "Время указано по часовому поясу вашего устройства.";

    const set =
        <K extends keyof EventFormState>(key: K) =>
        (value: EventFormState[K]) =>
            setForm((prev) => ({ ...prev, [key]: value }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (submitting || coverError) return;
        if (locationPending || timezoneState.loading) { setError("Дождитесь определения места и местного времени."); return; }
        const problem = validateForm(form, timezone);
        if (problem) {
            setError(problem);
            return;
        }
        setSubmitting(true);
        setError(null);
        try {
            const publish = (e.nativeEvent as SubmitEvent).submitter?.getAttribute("data-action") !== "draft";
            await onSubmit(formToInput(form, timezone), cover, publish);
        } catch (err) {
            setError(errorText(err));
            setSubmitting(false);
        }
    };

    return (
        <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
        <form
            onSubmit={handleSubmit}
            noValidate
            className="flex w-full flex-col gap-5 rounded-lg bg-cards-surface p-4 sm:p-8"
        >
            <fieldset disabled={submitting} className="flex min-w-0 flex-col gap-5">
            <div className="flex flex-col gap-1">
                <h1 className="text-h1 text-textprimary">{title}</h1>
                <p className="text-duration text-textsecondary">
                    Любой формат подойдёт: от концерта до «ищем четвёртого в теннис».
                </p>
            </div>

            <Section title="Что за движ">
                <EventCoverField
                    value={cover}
                    initialUrl={initialCoverUrl}
                    viewerId={userId}
                    disabled={submitting}
                    error={coverError}
                    onChange={setCover}
                    onError={setCoverError}
                />
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
                <EventTagField selected={form.tags} initialTags={initial?.tags} disabled={submitting} onChange={set("tags")} />
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
                <p role="status" className="text-small text-textsecondary">{timezoneHint}</p>
                {timezoneState.data?.warning && <Notice>{timezoneState.data.warning}</Notice>}
            </Section>

            <Section title="Где">
                <FormField label="Формат" htmlFor="format">
                    <Select<EventFormat> id="format" value={form.format} options={FORMAT_LABELS} onChange={set("format")} />
                </FormField>

                {form.format !== "ONLINE" && (
                        <EventLocationField
                            value={form.place}
                            profileCity={user?.id === userId ? user.city : null}
                            disabled={submitting}
                            onChange={set("place")}
                            onPendingChange={setLocationPending}
                        />
                )}

                {form.format !== "OFFLINE" && (
                    <FormField label="Ссылка на трансляцию" htmlFor="online-url" required>
                        <Input id="online-url" type="url" placeholder="https://" value={form.onlineUrl} onChange={set("onlineUrl")} />
                    </FormField>
                )}
            </Section>

            <Section title="Участие">
                <div className="grid gap-4 sm:grid-cols-2">
                    <FormField label="Цена, ₽" htmlFor="price" hint="Пусто или 0 — бесплатно">
                        <Input id="price" type="number" min={0} step="0.01" inputMode="decimal" value={form.price} onChange={set("price")} />
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
            </Section>

            {error && <Notice tone="error">{error}</Notice>}

            <div className="flex flex-wrap justify-end gap-2">
                <Button state="hover1" onClick={onCancel}>
                    Отмена
                </Button>
                {allowDraft && <Button type="submit" action="draft" state="hover2" disabled={submitting || Boolean(coverError)}>Сохранить черновик</Button>}
                <Button type="submit" state="fixed1" disabled={submitting || Boolean(coverError)}>
                    {submitting ? "Сохраняем событие и обложку…" : submitLabel}
                </Button>
            </div>
            </fieldset>
        </form>
        </section>
    );
};
