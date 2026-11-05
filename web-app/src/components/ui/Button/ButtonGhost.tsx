export interface ButtonGhostProps {
    className?: string;
    text: string;
    onClick?: () => void;
}

export const ButtonGhost = ({ className, text, onClick }: ButtonGhostProps) => (
    <button
        type="button"
        onClick={onClick}
        className={`inline-flex cursor-pointer items-center justify-center bg-transparent text-body text-textghost transition-opacity hover:opacity-70 ${className ?? ""}`}
    >
        {text}
    </button>
);
