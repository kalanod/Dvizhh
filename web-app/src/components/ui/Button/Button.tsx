import type { ReactNode } from "react";
import { useState } from "react";

export type ButtonState = "hover1" | "fixed1" | "disabled" | "hover2" | "fixed2";

interface ButtonProps {
    state?: ButtonState;
    children: ReactNode;
    className?: string;
    onClick?: () => void;
    type?: "button" | "submit" | "reset";
    ariaPressed?: boolean;
    ariaLabel?: string;
    title?: string;
    disabled?: boolean;
}

const stateClassMap: Record<ButtonState, string> = {
    hover1: "border-bordermain bg-borderlight",
    fixed1: "border-bordermain bg-borderlight shadow-hover",
    disabled: "border-bordermain bg-bordermain opacity-50 cursor-not-allowed",
    hover2: "border-borderlight bg-bordermain",
    fixed2: "border-borderlight bg-bordermain shadow-hover",
};

export const Button = ({
    state = "hover1",
    children,
    className = "",
    onClick,
    type = "button",
    ariaPressed,
    ariaLabel,
    title,
    disabled = false,
}: ButtonProps) => {
    const [isHovered, setIsHovered] = useState(false);

    const isDisabled = state === "disabled" || disabled;

    let currentState: ButtonState = isDisabled ? "disabled" : state;

    // Для hover1 при наведении переходим в fixed1
    if (!isDisabled && state === "hover1" && isHovered) {
        currentState = "fixed1";
    }

    // Для hover2 при наведении переходим в fixed2
    if (!isDisabled && state === "hover2" && isHovered) {
        currentState = "fixed2";
    }

    return (
        <button
            type={type}
            onClick={isDisabled ? undefined : onClick}
            aria-pressed={ariaPressed}
            aria-label={ariaLabel}
            title={title}
            disabled={isDisabled}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            className={`inline-flex h-[41px] w-fit shrink-0 cursor-pointer items-center justify-center gap-[10px] whitespace-nowrap rounded-lg border-2 px-[23px] py-0 text-buttons text-textthird transition-all duration-200 ${stateClassMap[currentState]} ${className}`}
        >
            {children}
        </button>
    );
};
