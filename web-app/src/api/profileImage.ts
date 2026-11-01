import type { ImageChange } from "../utils/media";
import { setAvatar, uploadImage } from "./media";

/** Retains a successful upload when assigning the avatar needs a retry. */
export function createAvatarSaver(userId: string) {
    let uploaded: { file: File; id: string } | undefined;
    return async (change: Exclude<ImageChange, { kind: "keep" }>) => {
        if (change.kind === "remove") return setAvatar(userId, null);
        if (uploaded?.file !== change.file) {
            const media = await uploadImage(userId, change.file);
            uploaded = { file: change.file, id: media.id };
        }
        return setAvatar(userId, uploaded.id);
    };
}
