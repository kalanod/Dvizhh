import { Link } from "react-router-dom";
import { hashtagSearchUrl, isHashtag, splitHashtags } from "../../../utils/hashtags";

/** Название с доступными с клавиатуры ссылками на поиск по хештегу. */
export const EventTitle = ({ title }: { title: string }) => (
    <>
        {splitHashtags(title).map((part, index) => isHashtag(part) ? (
            <Link
                key={index}
                to={hashtagSearchUrl(part)}
                onClick={(event) => event.stopPropagation()}
                className="text-textghost underline decoration-current underline-offset-2 hover:opacity-80 focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-2"
                aria-label={`Найти события с хештегом ${part}`}
            >
                {part}
            </Link>
        ) : part)}
    </>
);
