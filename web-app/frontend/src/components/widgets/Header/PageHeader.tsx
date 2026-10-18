import { useLocation, useNavigate } from "react-router-dom";
import { Avatar, Button } from "../../ui";
import { useCurrentUser } from "../../../hooks";

const navItems = [
    { label: "Афиша", path: "/" },
    { label: "Календарь", path: "/calendar" },
    { label: "Профиль", path: "/profile" },
];

export const PageHeader = () => {
    const navigate = useNavigate();
    const { pathname } = useLocation();
    const { user, signOut } = useCurrentUser();

    const isActive = (path: string) => (path === "/" ? pathname === "/" : pathname.startsWith(path));

    return (
        <header className="relative flex w-full flex-wrap items-center gap-[10px] rounded-2xl bg-background/90 px-[14px] py-[10px] shadow-card backdrop-blur">
            <button
                type="button"
                onClick={() => navigate("/")}
                className="flex flex-1 cursor-pointer items-center gap-3 text-left"
                aria-label="Движж — на главную"
            >
                <img src="/favicon.svg" alt="" className="h-[38px] w-[38px]" />
                <span className="text-logo text-textthird">
                    Движ<span className="text-borderlight">ж</span>
                </span>
            </button>

            <nav className="order-3 flex w-full items-center gap-[8px] overflow-x-auto sm:order-none sm:w-auto">
                {navItems.map((item) => (
                    <Button
                        key={item.path}
                        onClick={() => navigate(item.path)}
                        state={isActive(item.path) ? "fixed2" : "ghost"}
                        ariaPressed={isActive(item.path)}
                    >
                        {item.label}
                    </Button>
                ))}
            </nav>

            <div className="flex items-center gap-2">
                {user ? (
                    <>
                        <button
                            type="button"
                            onClick={() => navigate("/profile")}
                            className="flex cursor-pointer items-center gap-2 rounded-xl px-2 py-1 text-body font-bold text-textthird transition-colors hover:bg-white/5"
                            title={`@${user.username}`}
                        >
                            <Avatar name={user.display_name} seed={user.id} size="sm" />
                            <span className="hidden max-w-[140px] truncate md:inline">{user.display_name}</span>
                        </button>
                        <Button state="ghost" onClick={signOut}>
                            Выйти
                        </Button>
                    </>
                ) : (
                    <Button state="hover1" onClick={() => navigate("/login")}>
                        Войти
                    </Button>
                )}
            </div>
        </header>
    );
};
