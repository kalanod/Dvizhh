import { useState } from "react";
import { errorText, getCalendar } from "../../../api";
import { useAsync, useCurrentUser } from "../../../hooks";
import type { DvizhEvent } from "../../../models";
import { MainLayout } from "../../layouts";
import { Button, Loader, Notice } from "../../ui";
import { EventCard, LoginRequired } from "../../widgets";
import { formatMonth } from "../../../utils/format";

const groupByMonth = (events: DvizhEvent[]) => {
    const groups = new Map<string, DvizhEvent[]>();
    for (const event of events) {
        const month = formatMonth(event.starts_at);
        groups.set(month, [...(groups.get(month) ?? []), event]);
    }
    return [...groups.entries()];
};

export const CalendarPage = () => {
    const { userId, loading: userLoading } = useCurrentUser();

    return (
        <MainLayout>
            {userLoading ? (
                <Loader />
            ) : userId ? (
                <Calendar userId={userId} />
            ) : (
                <LoginRequired text="Войдите, чтобы собрать свой календарь" />
            )}
        </MainLayout>
    );
};

const Calendar = ({ userId }: { userId: string }) => {
    const [showPast, setShowPast] = useState(false);
    const { data, error, loading } = useAsync(() => getCalendar(userId), userId);
    const [now] = useState(() => Date.now());

    const isPast = (event: DvizhEvent) => new Date(event.ends_at ?? event.starts_at).getTime() < now;
    const events = (data ?? []).filter((event) => showPast || !isPast(event));
    const pastCount = (data ?? []).filter(isPast).length;

    return (
        <div className="flex w-full flex-col items-start gap-[10px] rounded-lg bg-background p-[10px]">
            <div className="flex w-full flex-wrap items-center justify-between gap-2">
                <h1 className="text-h1 text-textthird">Мой календарь</h1>
                {pastCount > 0 && (
                    <Button state={showPast ? "fixed1" : "hover1"} onClick={() => setShowPast((value) => !value)}>
                        {showPast ? "Скрыть прошедшие" : `Прошедшие (${pastCount})`}
                    </Button>
                )}
            </div>

            {loading && <Loader />}
            {error !== undefined && <Notice tone="error">{errorText(error)}</Notice>}
            {!loading && !error && events.length === 0 && (
                <div className="flex w-full items-center justify-center p-8">
                    <p className="text-h3 text-textthird">Здесь появятся события, на которые вы идёте</p>
                </div>
            )}

            {groupByMonth(events).map(([month, items]) => (
                <div key={month} className="flex w-full flex-col gap-[10px]">
                    <h2 className="text-h2 text-textthird">{month}</h2>
                    {items.map((event) => (
                        <EventCard key={event.id} event={event} className={isPast(event) ? "opacity-60" : ""} />
                    ))}
                </div>
            ))}
        </div>
    );
};
