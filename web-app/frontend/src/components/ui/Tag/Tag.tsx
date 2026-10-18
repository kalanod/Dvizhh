export type TagVariant = "topic" | "format" | "price" | "free" | "policy" | "muted";

interface TagProps {
    label: string;
    variant?: TagVariant;
    className?: string;
    onClick?: () => void;
}

const variantClassMap: Record<TagVariant, string> = {
    topic: "bg-tagtopic/12 text-tagtopic",
    format: "bg-tagformat/12 text-tagformat",
    price: "bg-tagprice/12 text-tagprice",
    free: "bg-tagfree/12 text-tagfree",
    policy: "bg-tagpolicy/12 text-tagpolicy",
    muted: "bg-tagmuted/15 text-textsecondary",
};

export const Tag = ({ label, variant = "topic", className = "", onClick }: TagProps) => {
    const classes = `inline-flex h-[24px] w-fit items-center justify-center whitespace-nowrap rounded-full px-[10px] text-small ${variantClassMap[variant]} ${className}`;

    if (onClick) {
        return (
            <button
                type="button"
                onClick={(e) => {
                    e.stopPropagation();
                    onClick();
                }}
                className={`${classes} cursor-pointer transition-opacity hover:opacity-75`}
            >
                {variant === "topic" ? `#${label}` : label}
            </button>
        );
    }

    return <span className={classes}>{variant === "topic" ? `#${label}` : label}</span>;
};
