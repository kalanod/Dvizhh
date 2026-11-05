import { useState, type ReactNode } from "react";
import { dateBadge } from "../../../utils/format";
import { mediaContentUrl } from "../../../utils/media";

interface CoverProps {
    startsAt: string;
    timeZone?: string;
    coverUrl?: string | null;
    viewerId?: string | null;
}

const CoverImage = ({ source, children }: { source: string | null; children: ReactNode }) => {
    const [failed, setFailed] = useState<string | null>(null);
    return source && failed !== source ? (
        <img
            src={source}
            alt="Обложка события"
            loading="lazy"
            className="h-full w-full object-cover"
            onError={() => setFailed(source)}
        />
    ) : children;
};

/** Обложка карточки; если изображения нет или оно недоступно, показывает дату. */
export const EventCoverMicro = ({ startsAt, timeZone, coverUrl, viewerId }: CoverProps) => {
    const badge = dateBadge(startsAt, timeZone);

    return (
        <div className="relative flex h-full w-full flex-col items-center justify-center overflow-hidden rounded bg-gradient-to-br from-success/70 to-success text-white">
            <CoverImage source={mediaContentUrl(coverUrl, viewerId)}>
                <div className="flex flex-col items-center">
                    <span className="text-h1">{badge.day}</span>
                    <span className="text-h3">{badge.month}</span>
                </div>
            </CoverImage>
        </div>
    );
};

/** Большая обложка страницы события с тем же поведением при отсутствии изображения. */
export const EventCoverMain = ({ startsAt, timeZone, coverUrl, viewerId }: CoverProps) => {
    const badge = dateBadge(startsAt, timeZone);

    return (
        <div className="h-[279px] w-[186px] shrink-0 self-center overflow-hidden rounded-lg bg-secondary max-sm:h-[160px] max-sm:w-full sm:self-start">
            <CoverImage source={mediaContentUrl(coverUrl, viewerId)}>
                <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-b from-borderlight to-bordermain text-textthird">
                    <span className="text-[64px] leading-none font-bold">{badge.day}</span>
                    <span className="text-h2">{badge.month}</span>
                </div>
            </CoverImage>
        </div>
    );
};
