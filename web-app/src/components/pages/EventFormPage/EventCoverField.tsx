import { ImagePicker, type ImagePickerProps } from "../../ui";

type EventCoverFieldProps = Pick<ImagePickerProps,
    "value" | "initialUrl" | "viewerId" | "disabled" | "error" | "onChange" | "onError"
>;

export const EventCoverField = (props: EventCoverFieldProps) => (
    <ImagePicker
        {...props}
        id="event-cover"
        label="Обложка события"
        removeLabel="Убрать обложку"
        removedHint="Обложка будет убрана после сохранения."
        emptyHint="Обложка необязательна."
    />
);
