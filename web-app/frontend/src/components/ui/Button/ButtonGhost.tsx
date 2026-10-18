export interface ButtonGhostProps {
    className?: string;
    text: string;
    onClick?: () => void;
}

/** Текстовая кнопка-ссылка из шаблона. */
export const ButtonGhost = ({ className, text, onClick }: ButtonGhostProps) => (
    <button
        type="button"
        onClick={onClick}
        className={`inline-flex cursor-pointer items-center justify-center bg-transparent text-body font-bold text-textghost transition-opacity hover:opacity-70 ${className ?? ""}`}
    >
        {text}
    </button>
);
