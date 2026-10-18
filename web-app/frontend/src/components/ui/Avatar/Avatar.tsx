const PALETTE = ["#6c4cf0", "#e8431f", "#0f8f84", "#b45309", "#c026d3", "#2563eb"];

const colorFor = (seed: string) => {
    let hash = 0;
    for (const char of seed) {
        hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
    }
    return PALETTE[hash % PALETTE.length];
};

interface AvatarProps {
    name: string;
    seed?: string;
    size?: "sm" | "md" | "lg";
    className?: string;
}

const sizeClassMap = {
    sm: "h-7 w-7 text-[12px]",
    md: "h-10 w-10 text-[15px]",
    lg: "h-20 w-20 text-[30px]",
};

/** Аватар-заглушка: первая буква имени на цветном фоне (медиа-аватары пока не отдаются API). */
export const Avatar = ({ name, seed, size = "md", className = "" }: AvatarProps) => (
    <span
        aria-hidden="true"
        style={{ backgroundColor: colorFor(seed ?? name) }}
        className={`inline-flex shrink-0 items-center justify-center rounded-full font-display font-semibold text-textthird uppercase ${sizeClassMap[size]} ${className}`}
    >
        {name.trim().charAt(0) || "?"}
    </span>
);
