import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { cancelEvent, deleteEvent, errorText, publishEvent, setCover, uploadMedia } from "../../../api";
import type { DvizhEvent } from "../../../models";
import { Button, FileButton, Notice } from "../../ui";

interface OrganizerPanelProps {
    event: DvizhEvent;
    userId: string;
    onChanged: () => void;
}

/** Управление событием: публикация черновика, обложка, отмена и удаление. */
export const OrganizerPanel = ({ event, userId, onChanged }: OrganizerPanelProps) => {
    const navigate = useNavigate();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const editable = event.status === "DRAFT" || event.status === "PUBLISHED";

    const run = async (action: () => Promise<unknown>, success: string) => {
        setBusy(true);
        setError(null);
        setMessage(null);
        try {
            await action();
            setMessage(success);
            onChanged();
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    };

    const handleCover = (file: File) =>
        run(async () => {
            const media = await uploadMedia(userId, file);
            await setCover(event.id, userId, media.id);
        }, "Обложка обновлена.");

    const handleCancel = () => {
        if (
            window.confirm(
                `Отменить «${event.title}»? Запись закроется, а участники, заявители и приглашённые получат уведомление. Вернуть событие будет нельзя.`,
            )
        ) {
            run(() => cancelEvent(event.id, userId), "Событие отменено, участники получили уведомление.");
        }
    };

    const handleDelete = async () => {
        if (!window.confirm(`Удалить событие «${event.title}»? Оно пропадёт из ленты и календарей.`)) {
            return;
        }
        setBusy(true);
        setError(null);
        try {
            await deleteEvent(event.id, userId);
            navigate("/my", { replace: true });
        } catch (err) {
            setError(errorText(err));
            setBusy(false);
        }
    };

    return (
        <div className="flex w-full flex-col gap-2">
            {event.status === "DRAFT" && (
                <Notice>Это черновик: его видите только вы. Опубликуйте, когда всё будет готово.</Notice>
            )}
            <div className="flex flex-wrap gap-2">
                {event.status === "DRAFT" && (
                    <Button
                        state="hover2"
                        className="!h-[30px] !px-4"
                        disabled={busy}
                        onClick={() => run(() => publishEvent(event.id, userId), "Событие опубликовано и появилось в ленте.")}
                    >
                        Опубликовать
                    </Button>
                )}
                {editable && (
                    <>
                        <Button state="fixed2" className="!h-[30px] !px-4" disabled={busy} onClick={() => navigate(`/events/${event.id}/edit`)}>
                            Редактировать
                        </Button>
                        <FileButton state="hover1" className="!h-[30px] !px-4" disabled={busy} onFile={handleCover}>
                            {event.cover_media_id ? "Сменить обложку" : "Загрузить обложку"}
                        </FileButton>
                        {event.cover_media_id && (
                            <Button
                                state="hover1"
                                className="!h-[30px] !px-4"
                                disabled={busy}
                                onClick={() => run(() => setCover(event.id, userId, null), "Обложка убрана.")}
                            >
                                Убрать обложку
                            </Button>
                        )}
                    </>
                )}
                {event.status === "PUBLISHED" && (
                    <Button state="hover1" className="!h-[30px] !px-4" disabled={busy} onClick={handleCancel}>
                        Отменить событие
                    </Button>
                )}
                <Button state="hover1" className="!h-[30px] !px-4" disabled={busy} onClick={handleDelete}>
                    Удалить
                </Button>
            </div>
            {busy && <span className="text-small text-textsecondary">Сохраняем…</span>}
            {message && !error && <span className="text-small text-textsuccess">{message}</span>}
            {error && <Notice tone="error">{error}</Notice>}
        </div>
    );
};
