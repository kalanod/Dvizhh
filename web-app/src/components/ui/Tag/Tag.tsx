/** Варианты тегов шаблона, переосмысленные для событий. */
export type TagVariant = "topic" | "format" | "price" | "free" | "policy" | "muted";

interface TagProps {
    label: string;
    variant?: TagVariant;
    className?: string;
    onClick?: () => void;
}

const variantClassMap: Record<TagVariant, string> = {
    topic: "bg-taggenre text-textthird",
    format: "bg-tagtrops text-textthird",
    price: "bg-tagauthor text-textthird",
    free: "bg-tagtype text-textthird",
    policy: "bg-taglanguage text-textthird",
    muted: "bg-secondary text-textthird",
};

export const Tag = ({ label, variant = "topic", className = "", onClick }: TagProps) => {
    const classes = `inline-flex h-[20px] w-fit items-center justify-center whitespace-nowrap rounded-lg px-[6px] ${variantClassMap[variant]} ${className}`;
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
            >
                {content}
            </button>
        );
    }

    return <div className={classes}>{content}</div>;
};
