/** Варианты тегов шаблона, переосмысленные для событий. */
import { tagColorStyle } from "../../../utils/tags";

export type TagVariant = "topic" | "format" | "price" | "free" | "policy" | "muted";

interface TagProps {
    label: string;
    variant?: TagVariant;
    className?: string;
    onClick?: () => void;
    color?: string;
}

const variantClassMap: Record<TagVariant, string> = {
    topic: "bg-taggenre text-textthird",
    format: "bg-tagtrops text-textthird",
    price: "bg-tagauthor text-textthird",
    free: "bg-tagtype text-textthird",
    policy: "bg-taglanguage text-textthird",
    muted: "bg-secondary text-textthird",
};

export const Tag = ({ label, variant = "topic", className = "", onClick, color }: TagProps) => {
    const classes = `inline-flex min-h-[20px] max-w-full w-fit items-center justify-center rounded-lg px-[6px] ${color ? "border text-textprimary" : variantClassMap[variant]} ${className}`;
    const style = color ? tagColorStyle(color) : undefined;
    const content = <span className="text-small">{label}</span>;

    if (onClick) {
        return (
            <button
                type="button"
                onClick={(e) => {
                    e.stopPropagation();
                    onClick();
                }}
                className={`${classes} cursor-pointer transition-opacity hover:opacity-80`}
                style={style}
            >
                {content}
            </button>
        );
    }

    return <div className={classes} style={style}>{content}</div>;
};
