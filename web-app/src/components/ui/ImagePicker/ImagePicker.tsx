import { useEffect, useState } from "react";
import { errorText, getMediaConfig } from "../../../api";
import { useAsync } from "../../../hooks";
import { mediaContentUrl, validateCoverFile, type ImageChange } from "../../../utils/media";
import { Button } from "../Button";
import { FormField } from "../FormField";
import { Notice } from "../Notice";

export interface ImagePickerProps {
    id: string;
    label: string;
    value: ImageChange;
    initialUrl?: string | null;
    viewerId: string;
    disabled: boolean;
    error: string | null;
    removeLabel: string;
    removedHint: string;
    emptyHint: string;
    previewClassName?: string;
    onChange: (value: ImageChange) => void;
    onError: (error: string | null) => void;
}

export const ImagePicker = ({ id, label, value, initialUrl, viewerId, disabled, error, removeLabel, removedHint, emptyHint, previewClassName = "h-48 w-full max-w-md object-contain", onChange, onError }: ImagePickerProps) => {
    const config = useAsync(getMediaConfig, "media-config");
    const [preview, setPreview] = useState<string | null>(null);
    const activePreview = value.kind === "file" ? preview : null;
    useEffect(() => () => {
        if (activePreview) URL.revokeObjectURL(activePreview);
    }, [activePreview]);
    const source = value.kind === "file"
        ? activePreview
        : value.kind === "keep" ? mediaContentUrl(initialUrl, viewerId) : null;

    return (
        <FormField
            label={label}
            htmlFor={id}
            hint={config.data
                ? `JPEG, PNG или WebP, до ${config.data.max_bytes / 1024 / 1024} МБ. ${emptyHint}`
                : emptyHint}
        >
            {source && (
                <img
                    src={source}
                    alt={`Предпросмотр: ${label.toLowerCase()}`}
                    className={`rounded-lg bg-secondary ${previewClassName}`}
                    onError={() => {
                        if (value.kind === "file") onError("Не удалось открыть изображение. Выберите другой файл.");
                    }}
                />
            )}
            <input
                id={id}
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
                    {removeLabel}
                </Button>
            )}
            {value.kind === "remove" && <span className="text-small text-textsecondary">{removedHint}</span>}
            {error && <Notice tone="error">{error}</Notice>}
        </FormField>
    );
};
