import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { errorText, getEvent } from "../../../api";
import { createEventSaver } from "../../../api/eventCover";
import { useAsync, useCurrentUser } from "../../../hooks";
import type { DvizhEvent } from "../../../models";
import { MainLayout } from "../../layouts";
import { Loader, Notice } from "../../ui";
import { LoginRequired } from "../../widgets";
import { EventForm } from "./EventForm";
import { formFromEvent } from "./formState";

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
            {id ? <EditEvent eventId={id} userId={userId} /> : <CreateEvent key={userId} userId={userId} />}
        </MainLayout>
    );
};

const CreateEvent = ({ userId }: { userId: string }) => {
    const navigate = useNavigate();
    const [save] = useState(() => createEventSaver(userId));

    return (
        <EventForm
            title="Новый движ"
            submitLabel="Опубликовать"
            userId={userId}
            onCancel={() => navigate(-1)}
            onSubmit={async (input, cover) => {
                const event = await save(input, cover);
                navigate(`/events/${event.id}`, { replace: true });
            }}
        />
    );
};

const EditEvent = ({ eventId, userId }: { eventId: string; userId: string }) => {
    const { data: event, error, loading } = useAsync(() => getEvent(eventId, userId), `${eventId}:${userId}`);

    if (loading) return <Loader />;
    if (!event) return <Notice tone="error">{errorText(error)}</Notice>;
    if (event.organizer?.id !== userId) {
        return <Notice tone="error">Редактировать событие может только организатор.</Notice>;
    }
    if (event.status !== "DRAFT" && event.status !== "PUBLISHED") {
        return <Notice>Редактирование этого события закрыто.</Notice>;
    }
    return <EditEventForm key={`${event.id}:${userId}`} event={event} userId={userId} />;
};

const EditEventForm = ({ event, userId }: { event: DvizhEvent; userId: string }) => {
    const navigate = useNavigate();
    const [initial] = useState(() => formFromEvent(event));
    const [save] = useState(() => createEventSaver(userId, event.id));

    return (
        <EventForm
            title="Редактирование"
            submitLabel="Сохранить"
            initial={initial}
            userId={userId}
            initialCoverUrl={event.cover_url}
            onCancel={() => navigate(`/events/${event.id}`)}
            onSubmit={async (input, cover) => {
                await save(input, cover);
                navigate(`/events/${event.id}`, { replace: true });
            }}
        />
    );
};
