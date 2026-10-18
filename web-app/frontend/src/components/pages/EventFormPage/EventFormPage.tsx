import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createEvent, errorText, getEvent, updateEvent } from "../../../api";
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
            {id ? <EditEvent eventId={id} userId={userId} /> : <CreateEvent userId={userId} />}
        </MainLayout>
    );
};

const CreateEvent = ({ userId }: { userId: string }) => {
    const navigate = useNavigate();

    return (
        <EventForm
            title="Новый движ"
            submitLabel="Опубликовать"
            onCancel={() => navigate(-1)}
            onSubmit={async (input) => {
                const event = await createEvent({ ...input, organizer_id: userId });
                navigate(`/events/${event.id}`, { replace: true });
            }}
        />
    );
};

const EditEvent = ({ eventId, userId }: { eventId: string; userId: string }) => {
    const { data: event, error, loading } = useAsync(() => getEvent(eventId), eventId);

    if (loading) return <Loader />;
    if (!event) return <Notice tone="error">{errorText(error)}</Notice>;
    if (event.organizer?.id !== userId) {
        return <Notice tone="error">Редактировать событие может только организатор.</Notice>;
    }
    return <EditEventForm event={event} />;
};

const EditEventForm = ({ event }: { event: DvizhEvent }) => {
    const navigate = useNavigate();
    const [initial] = useState(() => formFromEvent(event));

    return (
        <EventForm
            title="Редактирование"
            submitLabel="Сохранить"
            initial={initial}
            onCancel={() => navigate(`/events/${event.id}`)}
            onSubmit={async (input) => {
                await updateEvent(event.id, input);
                navigate(`/events/${event.id}`, { replace: true });
            }}
        />
    );
};
