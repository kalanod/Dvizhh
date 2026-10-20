import { dateBadge } from "../../../utils/format";

/** Обложка-заглушка карточки (BookCoverMicro шаблона) с датой события. */
export const EventCoverMicro = ({ startsAt, timeZone }: { startsAt: string; timeZone?: string }) => {
    const badge = dateBadge(startsAt, timeZone);

    return (
        <div className="relative flex h-[128px] w-[86px] flex-col items-center justify-center rounded bg-gradient-to-br from-success/70 to-success text-white">
            <span className="text-h1">{badge.day}</span>
            <span className="text-h3">{badge.month}</span>
        </div>
    );
};

/** Большая обложка-заглушка страницы события (BookCoverMain шаблона). */
export const EventCoverMain = ({ startsAt, timeZone }: { startsAt: string; timeZone?: string }) => {
    const badge = dateBadge(startsAt, timeZone);

    return (
        <div className="h-[279px] w-[186px] shrink-0 overflow-hidden rounded-lg bg-secondary">
            <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-b from-borderlight to-bordermain text-textthird">
                <span className="text-[64px] leading-none font-bold">{badge.day}</span>
                <span className="text-h2">{badge.month}</span>
            </div>
        </div>
    );
};
