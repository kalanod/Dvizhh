import type { ReactNode } from "react";
import { useRef } from "react";
import { Button, type ButtonState } from "../Button";

interface FileButtonProps {
    children: ReactNode;
    onFile: (file: File) => void;
    accept?: string;
    state?: ButtonState;
    disabled?: boolean;
    className?: string;
}

/** Кнопка в стиле Button, открывающая выбор файла. */
export const FileButton = ({
    children,
    onFile,
    accept = "image/jpeg,image/png,image/webp",
    state = "hover1",
    disabled,
    className,
}: FileButtonProps) => {
    const inputRef = useRef<HTMLInputElement>(null);

    return (
        <>
            <input
                ref={inputRef}
                type="file"
                accept={accept}
                hidden
                onChange={(e) => {
                    const file = e.target.files?.[0];
                    // Сброс, чтобы повторный выбор того же файла снова вызвал onChange.
                    e.target.value = "";
                    if (file) onFile(file);
                }}
            />
            <Button state={state} disabled={disabled} className={className} onClick={() => inputRef.current?.click()}>
                {children}
            </Button>
        </>
    );
};
