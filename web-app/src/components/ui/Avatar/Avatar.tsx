import { useState } from "react";

interface AvatarProps {
    name: string;
    src?: string | null;
    size?: "sm" | "md" | "lg";
    className?: string;
}

const sizeClassMap = {
    sm: "h-[28px] w-[28px] text-[13px]",
    md: "h-[37px] w-[37px] text-[16px]",
    lg: "h-[128px] w-[86px] text-[36px]",
};

/** Shows the profile image, falling back to an initial when absent or unavailable. */
export const Avatar = ({ name, src, size = "md", className = "" }: AvatarProps) => {
    const [failed, setFailed] = useState<string | null>(null);
    return (
        <span
            aria-hidden="true"
            className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-lg bg-secondary font-h1 font-bold text-textthird uppercase ${sizeClassMap[size]} ${className}`}
        >
            {src && src !== failed ? (
                <img src={src} alt="" className="h-full w-full object-cover" onError={() => setFailed(src)} />
            ) : name.trim().charAt(0) || "?"}
        </span>
    );
};
