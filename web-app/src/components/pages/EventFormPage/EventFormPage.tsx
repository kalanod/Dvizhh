import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
    createDraft,
    createEvent,
    errorText,
    getEvent,
    mediaSrc,
    publishEvent,
    setCover,
    updateEvent,
    uploadMedia,
} from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import type { DvizhEvent, EventInput } from "../../../models";
import { MainLayout } from "../../layouts";
import { Loader, Notice } from "../../ui";
import { LoginRequired } from "../../widgets";
import { EventForm, type CoverChange } from "./EventForm";
import { formFromEvent } from "./formState";

/** Сообщение для страницы события, если само событие сохранилось, а обложка — нет. */
interface EventPageNotice {
    notice?: string;
}

/**
 * Обложку можно назначить только существующему событию, поэтому она сохраняется вторым шагом.
 * Ошибку не пробрасываем: событие уже сохранено, повторная отправка формы создала бы дубль.
 */
const applyCover = async (eventId: string, userId: string, cover: CoverChange): Promise<EventPageNotice> => {
    if (cover === undefined) return {};
    try {
        const mediaId = cover ? (await uploadMedia(userId, cover)).id : null;
        await setCover(eventId, userId, mediaId);
        return {};
    } catch (err) {
        return { notice: `Событие сохранено, но обложку применить не удалось: ${errorText(err)}` };
    }
};

/** /events/new — создание, /events/:id/edit — редактирование. */
export const EventFormPage = () => {
    const { id } = useParams();
    const { userId, loading: userLoading } = useCurrentUser();

    if (userLoading) {
        return (
            <MainLayout showCreateButton={false}>
                <Loader />
            </MainLayout>
        );
    }

    if (!userId) {
        return (
            <MainLayout showCreateButton={false}>
                <LoginRequired text="Войдите, чтобы создать свой движ" />
            </MainLayout>
        );
    }

    return (
        <MainLayout showCreateButton={false}>
            {id ? <EditEvent eventId={id} userId={userId} /> : <CreateEvent userId={userId} />}
        </MainLayout>
    );
};

const CreateEvent = ({ userId }: { userId: string }) => {
    const navigate = useNavigate();

    const save = (create: typeof createEvent) => async (input: EventInput, cover: CoverChange) => {
        const event = await create({ ...input, organizer_id: userId });
        const state = await applyCover(event.id, userId, cover);
        navigate(`/events/${event.id}`, { replace: true, state });
    };

    return (
        <EventForm
            title="Новый движ"
            submitLabel="Опубликовать"
            secondary={{ label: "Сохранить черновик", onSubmit: save(createDraft) }}
            onCancel={() => navigate(-1)}
            onSubmit={save(createEvent)}
        />
    );
};

const EditEvent = ({ eventId, userId }: { eventId: string; userId: string }) => {
    const { data: event, error, loading } = useAsync((signal) => getEvent(eventId, userId, signal), `${eventId}:${userId}`);

    if (loading) return <Loader />;
    if (!event) return <Notice tone="error">{errorText(error)}</Notice>;
    if (event.organizer?.id !== userId) {
        return <Notice tone="error">Редактировать событие может только организатор.</Notice>;
    }
    if (event.status !== "DRAFT" && event.status !== "PUBLISHED") {
        return <Notice>Редактирование этого события закрыто.</Notice>;
    }
    return <EditEventForm event={event} userId={userId} />;
};

const EditEventForm = ({ event, userId }: { event: DvizhEvent; userId: string }) => {
    const navigate = useNavigate();
    const [initial] = useState(() => formFromEvent(event));

    const save = (publish: boolean) => async (input: EventInput, cover: CoverChange) => {
        await updateEvent(event.id, input, userId);
        const state = await applyCover(event.id, userId, cover);
        if (publish) {
            await publishEvent(event.id, userId);
        }
        navigate(`/events/${event.id}`, { replace: true, state });
    };

    return (
        <EventForm
            title={event.status === "DRAFT" ? "Черновик" : "Редактирование"}
            submitLabel="Сохранить"
            initial={initial}
            initialCoverSrc={mediaSrc(event.cover_url, userId)}
            secondary={event.status === "DRAFT" ? { label: "Сохранить и опубликовать", onSubmit: save(true) } : undefined}
            onCancel={() => navigate(`/events/${event.id}`)}
            onSubmit={save(false)}
        />
    );
};
