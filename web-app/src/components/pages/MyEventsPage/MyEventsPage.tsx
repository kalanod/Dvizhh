import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { errorText, listDismissed, listDrafts, listFavorites, listMyEvents } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import type { DvizhEvent } from "../../../models";
import { MainLayout } from "../../layouts";
import { Button, Loader } from "../../ui";
import { EventList, LoginRequired } from "../../widgets";

const PAGE_SIZE = 20;
const MAX_LIMIT = 100;

interface Tab {
    label: string;
    empty: string;
    load: (userId: string, limit: number, signal: AbortSignal) => Promise<DvizhEvent[]>;
    /** Карточка уходит из списка после переключателя — список нужно перечитать. */
    reloadOnPersonalChange?: boolean;
}

const TABS = {
    organized: {
        label: "Организую",
        empty: "Вы ещё не создали ни одного события — нажмите «+ Движ».",
        load: (userId, limit, signal) => listMyEvents(userId, "organized", { limit, signal }),
    },
    drafts: {
        label: "Черновики",
        empty: "Черновиков нет. Сохраните событие как черновик, чтобы доработать его позже.",
        load: (userId, limit, signal) => listDrafts(userId, { limit, signal }),
    },
    participating: {
        label: "Иду",
        empty: "Вы пока никуда не записались.",
        load: (userId, limit, signal) => listMyEvents(userId, "participating", { limit, signal }),
    },
    requested: {
        label: "Заявки",
        empty: "Нет заявок, ожидающих решения организатора.",
        load: (userId, limit, signal) => listMyEvents(userId, "requested", { limit, signal }),
    },
    favorites: {
        label: "Избранное",
        empty: "Нажмите «☆ В избранное» на событии, чтобы сохранить его здесь.",
        load: (userId, limit, signal) => listFavorites(userId, { limit, signal }),
        reloadOnPersonalChange: true,
    },
    dismissed: {
        label: "Скрытые",
        empty: "Скрытых событий нет. «✕ Не интересно» убирает событие из вашей ленты.",
        load: (userId, limit, signal) => listDismissed(userId, { limit, signal }),
        reloadOnPersonalChange: true,
    },
} satisfies Record<string, Tab>;

type TabKey = keyof typeof TABS;

const isTab = (value: string | null): value is TabKey => value !== null && value in TABS;

export const MyEventsPage = () => {
    const { userId, loading } = useCurrentUser();

    return (
        <MainLayout>
            {loading ? <Loader /> : userId ? <MyEvents userId={userId} /> : <LoginRequired text="Войдите, чтобы видеть свои события" />}
        </MainLayout>
    );
};

const MyEvents = ({ userId }: { userId: string }) => {
    const [searchParams, setSearchParams] = useSearchParams();
    const param = searchParams.get("tab");
    const tab: TabKey = isTab(param) ? param : "organized";

    return (
        <div className="flex w-full flex-col gap-[10px]">
            <nav className="flex w-full flex-wrap gap-2 rounded-lg bg-background p-[10px]" aria-label="Мои события">
                {(Object.entries(TABS) as [TabKey, Tab][]).map(([key, { label }]) => (
                    <Button
                        key={key}
                        state={key === tab ? "fixed1" : "hover2"}
                        ariaPressed={key === tab}
                        className="max-sm:flex-1"
                        onClick={() => setSearchParams(key === "organized" ? {} : { tab: key }, { replace: true })}
                    >
                        {label}
                    </Button>
                ))}
            </nav>
            {/* key сбрасывает «Показать ещё» при смене вкладки. */}
            <TabEvents key={tab} userId={userId} tab={TABS[tab]} />
        </div>
    );
};

const TabEvents = ({ userId, tab }: { userId: string; tab: Tab }) => {
    const [limit, setLimit] = useState(PAGE_SIZE);
    const { data, error, loading, reload } = useAsync((signal) => tab.load(userId, limit, signal), `${tab.label}:${userId}:${limit}`);
    const hasMore = (data?.length ?? 0) >= limit && limit < MAX_LIMIT;

    return (
        <EventList
            title={tab.label}
            events={data}
            loading={loading}
            error={error ? errorText(error) : null}
            emptyText={tab.empty}
            onPersonalChange={tab.reloadOnPersonalChange ? reload : undefined}
            footer={
                hasMore && !loading ? (
                    <Button state="hover1" className="self-center" onClick={() => setLimit((value) => Math.min(value + PAGE_SIZE, MAX_LIMIT))}>
                        Показать ещё
                    </Button>
                ) : null
            }
        />
    );
};
