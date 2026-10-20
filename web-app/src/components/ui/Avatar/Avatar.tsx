interface AvatarProps {
    name: string;
    size?: "sm" | "md" | "lg";
    className?: string;
}

const sizeClassMap = {
    sm: "h-[28px] w-[28px] text-[13px]",
    md: "h-[37px] w-[37px] text-[16px]",
    lg: "h-[128px] w-[86px] text-[36px]",
};

/** Аватар-заглушка в стиле ButtonImg шаблона: первая буква имени. */
export const Avatar = ({ name, size = "md", className = "" }: AvatarProps) => (
    <span
        aria-hidden="true"
        className={`inline-flex shrink-0 items-center justify-center rounded-lg bg-secondary font-h1 font-bold text-textthird uppercase ${sizeClassMap[size]} ${className}`}
    >
        {name.trim().charAt(0) || "?"}
    </span>
);
