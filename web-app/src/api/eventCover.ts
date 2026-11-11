import type { EventInput } from "../models";
import type { EventCoverChange } from "../utils/media";
import { errorText } from "./client";
import { createDraftEvent, publishEvent, updateEvent } from "./events";
import { setEventCover, uploadImage } from "./media";

/** Keeps a known event/upload across retries so saving a cover does not duplicate events. */
export function createEventSaver(actorId: string, existingEventId?: string) {
    let eventId = existingEventId;
    let uploaded: { file: File; id: string } | undefined;

    return async (input: EventInput, cover: EventCoverChange, publish = true) => {
        let event = eventId
            ? await updateEvent(eventId, input, actorId)
            : await createDraftEvent({ ...input, organizer_id: actorId });
        eventId = event.id;
        try {
            if (cover.kind === "file") {
                if (uploaded?.file !== cover.file) {
                    const media = await uploadImage(actorId, cover.file);
                    uploaded = { file: cover.file, id: media.id };
                }
                event = await setEventCover(eventId, actorId, uploaded.id);
            } else if (cover.kind === "remove") {
                event = await setEventCover(eventId, actorId, null);
            }
        } catch (error) {
            const state = existingEventId
                ? "Параметры события сохранены, но обложку сохранить не удалось."
                : "Событие пока не опубликовано: не удалось сохранить обложку.";
            throw new Error(`${state} ${errorText(error)} Повторите сохранение.`);
        }
        return existingEventId || !publish ? event : publishEvent(eventId, actorId);
    };
}
