import { useState, type ReactNode } from "react";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";

interface ImageViewerProps {
    src?: string | null;
    alt: string;
    children: ReactNode;
    className?: string;
    disabled?: boolean;
}

/** One accessible image dialog for profile photos and event covers. */
export const ImageViewer = ({ src, alt, children, className = "", disabled = false }: ImageViewerProps) => {
    const [openedSource, setOpenedSource] = useState<string | null>(null);
    const [failed, setFailed] = useState<string | null>(null);
    if (!src || disabled) return children;

    return <>
        <button type="button" aria-label={`Открыть изображение: ${alt}`} aria-haspopup="dialog"
            className={`cursor-zoom-in rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-borderfocus focus-visible:ring-offset-2 ${className}`}
            onClick={(event) => { event.stopPropagation(); setFailed(null); setOpenedSource(src); }}>
            {children}
        </button>
        <Dialog open={openedSource === src} onClose={() => setOpenedSource(null)}
            aria-label={alt} maxWidth={false}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => event.stopPropagation()}
            slotProps={{
                backdrop: { sx: { backgroundColor: "rgba(10, 6, 30, 0.85)" } },
                paper: { sx: { position: "relative", m: { xs: 1, sm: 3 }, width: "fit-content", minWidth: "120px", maxWidth: "min(1100px, calc(100vw - 16px))", maxHeight: "calc(100dvh - 16px)", borderRadius: "12px", backgroundColor: "#141020", color: "white", overflow: "hidden", pt: "48px" } },
            }}>
            <IconButton autoFocus aria-label="Закрыть изображение" onClick={() => setOpenedSource(null)}
                sx={{ position: "absolute", right: 6, top: 4, color: "white", width: 40, height: 40 }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="m6 6 12 12M18 6 6 18" />
                </svg>
            </IconButton>
            {failed === src
                ? <p role="alert" className="px-6 py-12 text-center text-body">Не удалось загрузить изображение.</p>
                : <img src={src} alt={alt} onError={() => setFailed(src)}
                    style={{ display: "block", width: "auto", maxWidth: "100%", height: "auto", maxHeight: "min(80dvh, 850px)", objectFit: "contain", margin: "0 auto" }} />}
        </Dialog>
    </>;
};
