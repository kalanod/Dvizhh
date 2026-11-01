import type { MediaConfig } from "../api/media";

export type ImageChange =
    | { kind: "keep" }
    | { kind: "remove" }
    | { kind: "file"; file: File };

export type EventCoverChange = ImageChange;

export function mediaContentUrl(url?: string | null, viewerId?: string | null): string | null {
    if (!url) return null;
    if (!viewerId || !url.startsWith("/api/media/")) return url;
    return `${url}${url.includes("?") ? "&" : "?"}viewer_id=${encodeURIComponent(viewerId)}`;
}

export function validateCoverFile(file: File, config: MediaConfig): string | null {
    const mimeFormats: Record<string, string> = {
        "image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP",
    };
    const extensionFormats: Record<string, string> = {
        jpg: "JPEG", jpeg: "JPEG", png: "PNG", webp: "WEBP",
    };
    const format = file.type
        ? mimeFormats[file.type]
        : extensionFormats[file.name.split(".").pop()?.toLowerCase() ?? ""];
    if (!format || !config.formats.includes(format)) return "Выберите JPEG, PNG или WebP.";
    if (file.size === 0) return "Файл пустой. Выберите другое изображение.";
    if (file.size > config.max_bytes) {
        return `Изображение должно быть не больше ${config.max_bytes / 1024 / 1024} МБ.`;
    }
    return null;
}
