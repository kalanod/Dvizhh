import { useEffect, useState } from "react";
import { errorText, getMediaConfig } from "../../../api";
import { useAsync } from "../../../hooks";
import { mediaContentUrl, validateCoverFile, type EventCoverChange } from "../../../utils/media";
import { Button, FormField, Notice } from "../../ui";

interface EventCoverFieldProps {
    value: EventCoverChange;
    initialUrl?: string | null;
    viewerId: string;
    disabled: boolean;
    error: string | null;
    onChange: (value: EventCoverChange) => void;
    onError: (error: string | null) => void;
}

export const EventCoverField = ({ value, initialUrl, viewerId, disabled, error, onChange, onError }: EventCoverFieldProps) => {
    const config = useAsync(getMediaConfig, "media-config");
    const [preview, setPreview] = useState<string | null>(null);
    useEffect(() => () => {
        if (preview) URL.revokeObjectURL(preview);
    }, [preview]);
    const source = value.kind === "file"
        ? preview
        : value.kind === "keep" ? mediaContentUrl(initialUrl, viewerId) : null;

    return (
        <FormField
            label="Обложка события"
            htmlFor="event-cover"
            hint={config.data
                ? `JPEG, PNG или WebP, до ${config.data.max_bytes / 1024 / 1024} МБ. Необязательно.`
                : "Обложка необязательна."}
        >
            {source && (
                <img
                    src={source}
                    alt="Предпросмотр обложки события"
                    className="h-48 w-full max-w-md rounded-lg bg-secondary object-contain"
                    onError={() => {
                        if (value.kind === "file") onError("Не удалось открыть изображение. Выберите другой файл.");
                    }}
                />
            )}
            <input
                id="event-cover"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                disabled={disabled || !config.data}
                className="max-w-full text-body text-textprimary file:mr-3 file:cursor-pointer file:rounded-lg file:border-2 file:border-bordermain file:bg-borderlight file:px-4 file:py-2 file:text-textthird disabled:opacity-50"
                onChange={(event) => {
                    const file = event.currentTarget.files?.[0];
                    event.currentTarget.value = "";
                    if (!file || !config.data) return;
                    const problem = validateCoverFile(file, config.data);
                    onError(problem);
                    if (problem) return;
                    setPreview(URL.createObjectURL(file));
                    onChange({ kind: "file", file });
                }}
            />
            {config.loading && <span role="status" className="text-small text-textsecondary">Проверяем ограничения загрузки…</span>}
            {config.error !== undefined && (
                <Notice tone="error">
                    Не удалось получить ограничения загрузки. {errorText(config.error)}
                    <Button onClick={config.reload} disabled={disabled}>Повторить</Button>
                </Notice>
            )}
            {(source || error) && (
                <Button
                    disabled={disabled}
                    onClick={() => {
                        setPreview(null);
                        onChange({ kind: "remove" });
                        onError(null);
                    }}
                >
                    Убрать обложку
                </Button>
            )}
            {value.kind === "remove" && <span className="text-small text-textsecondary">Обложка будет убрана после сохранения.</span>}
            {error && <Notice tone="error">{error}</Notice>}
        </FormField>
    );
};
