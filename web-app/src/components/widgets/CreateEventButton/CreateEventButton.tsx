import { useNavigate } from "react-router-dom";
import { useCurrentUser } from "../../../hooks";
import { Button } from "../../ui";

/** Постоянная кнопка быстрого создания события «Движ». */
export const CreateEventButton = () => {
    const navigate = useNavigate();
    const { userId } = useCurrentUser();

    return (
        <div className="fixed right-6 bottom-6 z-40">
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
