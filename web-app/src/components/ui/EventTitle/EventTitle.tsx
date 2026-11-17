import Link from "@mui/material/Link";
import { Link as RouterLink } from "react-router-dom";
import { hashtagSearchUrl, isHashtag, splitHashtags } from "../../../utils/hashtags";

/** Название с доступными с клавиатуры ссылками на поиск по хештегу. */
export const EventTitle = ({ title }: { title: string }) => (
    <>
        {splitHashtags(title).map((part, index) => isHashtag(part) ? (
            <Link
                key={index}
                component={RouterLink}
                to={hashtagSearchUrl(part)}
                onClick={(event) => event.stopPropagation()}
                underline="always"
                sx={{
                    color: "var(--color-bordermain)", font: "inherit", textUnderlineOffset: "3px",
                    textDecorationColor: "currentColor", transition: "opacity 180ms",
                    "&:hover": { opacity: 0.8 },
                    "&:focus-visible": { borderRadius: "2px", outline: "2px solid var(--color-borderfocus)", outlineOffset: "2px" },
                }}
                aria-label={`Найти события с хештегом ${part}`}
            >
                {part}
            </Link>
        ) : part)}
    </>
);
