import type { ReactNode } from "react";
import { useState } from "react";

/**
 * Состояния кнопки из шаблона: hover1/hover2 при наведении переходят в fixed1/fixed2.
 * 1 — акцентная (коралловая) кнопка, 2 — фиолетовая, ghost — контурная на тёмном фоне,
 * outline — контурная на светлой карточке (отмена, вторичные действия).
 */
export type ButtonState = "hover1" | "fixed1" | "disabled" | "hover2" | "fixed2" | "ghost" | "outline";

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
    hover1: "border-borderlight bg-borderlight text-textthird",
    fixed1: "border-borderlight bg-borderlight text-textthird shadow-hover",
    disabled: "border-secondary bg-secondary text-textthird opacity-50 cursor-not-allowed",
    hover2: "border-bordermain bg-bordermain text-textthird",
    fixed2: "border-bordermain bg-bordermain text-textthird shadow-hover",
    ghost: "border-textmuted/40 bg-transparent text-textmuted hover:border-textmuted hover:text-textthird",
    outline: "border-bordersoft bg-transparent text-textsecondary hover:border-bordererror hover:text-texterror",
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

    if (!isDisabled && state === "hover1" && isHovered) {
        currentState = "fixed1";
    }

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
            className={`inline-flex h-[41px] w-fit shrink-0 cursor-pointer items-center justify-center gap-[8px] whitespace-nowrap rounded-xl border-2 px-[20px] py-0 text-buttons transition-all duration-200 ${stateClassMap[currentState]} ${className}`}
        >
            {children}
        </button>
    );
};
