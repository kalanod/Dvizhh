import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "../../ui";

export const LoginRequired = ({ text }: { text: string }) => {
    const navigate = useNavigate();
    const { pathname } = useLocation();

    return (
        <section className="flex w-full flex-col gap-5 rounded-lg bg-background p-[10px]">
            <div className="flex w-full flex-col items-center gap-5 rounded-lg bg-cards-surface p-4 sm:p-8">
                <p className="text-h2 text-textprimary">{text}</p>
                <div className="flex flex-wrap justify-center gap-2">
                    <Button state="hover1" onClick={() => navigate(`/login?next=${encodeURIComponent(pathname)}`)}>
                        Войти
                    </Button>
                    <Button state="hover2" onClick={() => navigate(`/register?next=${encodeURIComponent(pathname)}`)}>
                        Зарегистрироваться
                    </Button>
                </div>
            </div>
        </section>
    );
};
