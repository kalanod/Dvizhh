import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "../../ui";

export const LoginRequired = ({ text }: { text: string }) => {
    const navigate = useNavigate();
    const { pathname } = useLocation();

    return (
        <div className="flex w-full flex-col items-center gap-4 rounded-2xl bg-background/90 px-6 py-14 text-center shadow-card">
            <p className="text-h2 text-textthird">{text}</p>
            <div className="flex flex-wrap justify-center gap-2">
                <Button state="hover1" onClick={() => navigate(`/login?next=${encodeURIComponent(pathname)}`)}>
                    Войти
                </Button>
                <Button state="ghost" onClick={() => navigate(`/register?next=${encodeURIComponent(pathname)}`)}>
                    Зарегистрироваться
                </Button>
            </div>
        </div>
    );
};
