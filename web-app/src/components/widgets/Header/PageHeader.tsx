import { useLocation, useNavigate } from "react-router-dom";
import { Avatar, Button } from "../../ui";
import { useCurrentUser } from "../../../hooks";
import logo from "../../../assets/images/logo.svg";

const navButtons = [
    { label: "Афиша", path: "/" },
    { label: "Мой календарь", path: "/calendar" },
    { label: "Профиль", path: "/profile" },
];

export const PageHeader = () => {
    const navigate = useNavigate();
    const { pathname } = useLocation();
    const { user, signOut } = useCurrentUser();

    const isActive = (path: string) => (path === "/" ? pathname === "/" : pathname.startsWith(path));

    return (
        <header className="relative flex w-full flex-wrap items-center gap-[10px] overflow-hidden rounded-lg bg-background px-[10px] py-2">
            <img src={logo} alt="Движж" className="h-[35px] w-[49px] cursor-pointer" onClick={() => navigate("/")} />
            <span
                className="flex flex-1 cursor-pointer items-center italic text-alexsandria text-textprimary"
                onClick={() => navigate("/")}
            >
                {/* Отдельный span, чтобы градиент шёл по ширине текста, а не всего flex-1 блока. */}
                <span className="bg-gradient-to-r from-cards-surface via-borderfocus to-textghost bg-clip-text pr-1 text-transparent">
                    Движж
                </span>
            </span>
            <nav className="flex flex-wrap items-center gap-[10px]">
                {navButtons.map(({ label, path }) => (
                    <Button
                        key={path}
                        onClick={() => navigate(path)}
                        state={isActive(path) ? "fixed1" : "hover1"}
                        ariaPressed={isActive(path)}
                    >
                        {label}
                    </Button>
                ))}
            </nav>
            <div className="flex items-center gap-2">
                {user ? (
                    <>
                        <button
                            type="button"
                            aria-label="Профиль"
                            title={`${user.display_name} (@${user.username})`}
                            onClick={() => navigate("/profile")}
                            className="cursor-pointer transition-opacity hover:opacity-80"
                        >
                            <Avatar name={user.display_name} />
                        </button>
                        <Button state="hover2" onClick={signOut}>
                            Выйти
                        </Button>
                    </>
                ) : (
                    <Button state="hover2" onClick={() => navigate("/login")}>
                        Войти
                    </Button>
                )}
            </div>
        </header>
    );
};
