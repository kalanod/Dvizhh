import { useNavigate } from "react-router-dom";
import { useCurrentUser } from "../../../hooks";
import { Button } from "../../ui";

/** Постоянная кнопка быстрого создания события «Движ». */
export const CreateEventButton = () => {
    const navigate = useNavigate();
    const { userId } = useCurrentUser();

    return (
        <div className="fixed right-4 bottom-4 z-40 sm:right-6 sm:bottom-6">
            <Button
                state="fixed2"
                ariaLabel="Создать событие"
                onClick={() => navigate(userId ? "/events/new" : "/login?next=/events/new")}
            >
                + Движ
            </Button>
        </div>
    );
};
