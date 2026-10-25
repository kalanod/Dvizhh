import { dateBadge } from "../../../utils/format";

interface CoverProps {
    startsAt: string;
    timeZone?: string;
    /** Загруженная обложка; без неё — заглушка с датой. */
    src?: string | null;
}

/** Обложка-заглушка карточки (BookCoverMicro шаблона) с датой события. */
export const EventCoverMicro = ({ startsAt, timeZone, src }: CoverProps) => {
    const badge = dateBadge(startsAt, timeZone);

    if (src) {
        return (
            <div className="relative h-[128px] w-[86px] overflow-hidden rounded">
                <img src={src} alt="" className="h-full w-full object-cover" />
                <span className="absolute inset-x-0 bottom-0 bg-black/45 py-0.5 text-center text-small text-white">
                    {badge.day} {badge.month}
                </span>
            </div>
        );
    }

    return (
        <div className="relative flex h-[128px] w-[86px] flex-col items-center justify-center rounded bg-gradient-to-br from-success/70 to-success text-white">
            <span className="text-h1">{badge.day}</span>
            <span className="text-h3">{badge.month}</span>
        </div>
    );
};

/** Большая обложка-заглушка страницы события (BookCoverMain шаблона). */
export const EventCoverMain = ({ startsAt, timeZone, src }: CoverProps) => {
    const badge = dateBadge(startsAt, timeZone);

    return (
        <div className="h-[279px] w-[186px] shrink-0 self-center overflow-hidden rounded-lg bg-secondary max-sm:h-[160px] max-sm:w-full sm:self-start">
            {src ? (
                <img src={src} alt="Обложка события" className="h-full w-full object-cover" />
            ) : (
                <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-b from-borderlight to-bordermain text-textthird">
                    <span className="text-[64px] leading-none font-bold">{badge.day}</span>
                    <span className="text-h2">{badge.month}</span>
                </div>
            )}
        </div>
    );
};
