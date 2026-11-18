import { useEffect, useRef } from "react";
import type { DvizhEvent } from "../models";
import { recordInteraction } from "../utils/interactions";

const seenPages = new Map<string, Set<string>>();
const MAX_TRACKED_PAGES = 128;

export function useEventImpression(event: DvizhEvent, userId: string | null, hidden: boolean) {
    const element = useRef<HTMLElement>(null);
    const lastImpression = useRef<{ event: DvizhEvent; userId: string } | null>(null);

    useEffect(() => {
        const target = element.current;
        if (!target || !userId || hidden || typeof IntersectionObserver === "undefined") return;
        if (lastImpression.current?.event === event && lastImpression.current.userId === userId) return;

        const origin = event.interactionOrigin;
        const page = origin ? `${userId}:${origin.session_id}:${origin.request_id}` : undefined;
        if (page && seenPages.get(page)?.has(event.id)) return;

        let stopped = false;
        const observer = new IntersectionObserver((entries) => {
            if (stopped || document.visibilityState !== "visible" || !entries.some((entry) => entry.isIntersecting && entry.intersectionRatio > 0)) return;
            stop();
            if (page && seenPages.get(page)?.has(event.id)) return;
            if (!recordInteraction(userId, event.id, "IMPRESSION", origin)) return;
            lastImpression.current = { event, userId };
            if (page) {
                const items = seenPages.get(page) ?? new Set<string>();
                items.add(event.id);
                seenPages.set(page, items);
                if (seenPages.size > MAX_TRACKED_PAGES) {
                    const oldest = seenPages.keys().next().value;
                    if (oldest) seenPages.delete(oldest);
                }
            }
        });
        const observe = () => {
            observer.disconnect();
            observer.takeRecords();
            if (document.visibilityState === "visible") observer.observe(target);
        };
        const stop = () => {
            stopped = true;
            observer.disconnect();
            document.removeEventListener("visibilitychange", observe);
        };
        observe();
        document.addEventListener("visibilitychange", observe);
        return stop;
    }, [event, hidden, userId]);

    return element;
}
