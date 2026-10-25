import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Avatar, Button } from "../../ui";
import { mediaSrc } from "../../../api";
import { useCurrentUser, useInboxCount } from "../../../hooks";
import logo from "../../../assets/images/logo.svg";

const navButtons = [
    { label: "Афиша", path: "/" },
    { label: "Мой календарь", path: "/calendar" },
    { label: "Мои события", path: "/my" },
    { label: "Профиль", path: "/profile" },
];

export const PageHeader = () => {
    const navigate = useNavigate();
    const { pathname } = useLocation();
    const { userId, user, signOut } = useCurrentUser();
    const inboxCount = useInboxCount(userId);
    // Меню-бургер на экранах уже lg; на широких навигация всегда видна.
    const [menuOpen, setMenuOpen] = useState(false);

    const go = (path: string) => {
        setMenuOpen(false);
        navigate(path);
    };

    const isActive = (path: string) => (path === "/" ? pathname === "/" : pathname.startsWith(path));

    return (
        <header className="relative flex w-full flex-wrap items-center gap-[10px] overflow-hidden rounded-lg bg-background px-[10px] py-2">
            <img src={logo} alt="Движж" className="h-[35px] w-[49px] cursor-pointer" onClick={() => go("/")} />
            <span className="flex flex-1 cursor-pointer items-center italic text-alexsandria text-textprimary" onClick={() => go("/")}>
                {/* Отдельный span, чтобы градиент шёл по ширине текста, а не всего flex-1 блока. */}
                <span className="bg-gradient-to-r from-cards-surface via-borderfocus to-textghost bg-clip-text pr-1 text-transparent">
                    Движж
                </span>
            </span>
            <button
                type="button"
                aria-label={menuOpen ? "Закрыть меню" : "Открыть меню"}
                aria-expanded={menuOpen}
                aria-controls="header-menu"
                onClick={() => setMenuOpen((value) => !value)}
                className="inline-flex h-[41px] w-[41px] shrink-0 cursor-pointer items-center justify-center rounded-lg border-2 border-borderlight bg-bordermain text-textthird lg:hidden"
            >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path
                        d={menuOpen ? "M6 6L18 18M18 6L6 18" : "M4 7H20M4 12H20M4 17H20"}
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                    />
                </svg>
            </button>
            <div
                id="header-menu"
                className={`${menuOpen ? "flex" : "hidden"} w-full flex-col gap-[10px] lg:flex lg:w-auto lg:flex-row lg:items-center`}
            >
                <nav className="flex flex-col gap-[10px] lg:flex-row lg:flex-wrap lg:items-center">
                    {navButtons.map(({ label, path }) => (
                        <Button
                            key={path}
                            className="max-lg:!w-full"
                            onClick={() => go(path)}
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
                                aria-label={inboxCount > 0 ? `Уведомления: ${inboxCount} новых` : "Уведомления"}
                                title="Уведомления, приглашения и заявки в друзья"
                                onClick={() => go("/notifications")}
                                className={`relative inline-flex h-[37px] w-[37px] shrink-0 cursor-pointer items-center justify-center rounded-lg border-2 text-textthird transition-all hover:shadow-hover ${
                                    isActive("/notifications") ? "border-bordermain bg-borderlight shadow-hover" : "border-borderlight bg-bordermain"
                                }`}
                            >
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                                    <path
                                        d="M6 9a6 6 0 1 1 12 0c0 4 1.5 6 2.5 7H3.5C4.5 15 6 13 6 9ZM10 19.5a2 2 0 0 0 4 0"
                                        stroke="currentColor"
                                        strokeWidth="2"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    />
                                </svg>
                                {inboxCount > 0 && (
                                    <span className="absolute -top-1.5 -right-1.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-error px-1 text-[11px] leading-none font-bold text-white">
                                        {inboxCount >= 100 ? "99+" : inboxCount}
                                    </span>
                                )}
                            </button>
                            <button
                                type="button"
                                aria-label="Профиль"
                                title={`${user.display_name} (@${user.username})`}
                                onClick={() => go("/profile")}
                                className="cursor-pointer transition-opacity hover:opacity-80"
                            >
                                <Avatar name={user.display_name} src={mediaSrc(user.avatar_url, user.id)} />
                            </button>
                            <Button
                                state="hover2"
                                className="max-lg:flex-1"
                                onClick={() => {
                                    setMenuOpen(false);
                                    signOut();
                                }}
                            >
                                Выйти
                            </Button>
                        </>
                    ) : (
                        <Button state="hover2" className="max-lg:!w-full" onClick={() => go("/login")}>
                            Войти
                        </Button>
                    )}
                </div>
            </div>
        </header>
    );
};
