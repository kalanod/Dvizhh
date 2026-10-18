import { useNavigate } from "react-router-dom";
import { useCurrentUser } from "../../../hooks";

/** Постоянная заметная кнопка быстрого создания события «Движ». */
export const CreateEventButton = () => {
    const navigate = useNavigate();
    const { userId } = useCurrentUser();

    return (
        <button
            type="button"
            onClick={() => navigate(userId ? "/events/new" : "/login?next=/events/new")}
            className="fixed right-5 bottom-5 z-40 inline-flex h-[56px] cursor-pointer items-center gap-2 rounded-full bg-gradient-to-r from-borderlight to-bordermain px-6 font-display text-[16px] font-semibold text-textthird shadow-hover transition-transform hover:scale-105 active:scale-95"
            aria-label="Создать событие"
        >
            <span className="text-[24px] leading-none">+</span>
            Движ
        </button>
    );
};
