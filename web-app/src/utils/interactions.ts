import { ApiError } from "../api/client";
import { postInteractions } from "../api/interactions";
import type { Interaction, InteractionOrigin, InteractionType } from "../models/interaction";

const BATCH_SIZE = 20;
const BATCH_DELAY_MS = 250;
const INITIAL_RETRY_MS = 1000;
const MAX_RETRY_MS = 60_000;
const queues = new Map<string, Interaction[]>();
let active: { userId: string; schedule: () => void; resume: () => void } | undefined;

const storageKey = (userId: string) => `dvizh.interactions.${userId}`;

function queueFor(userId: string): Interaction[] {
    let queue = queues.get(userId);
    if (queue) return queue;
    queue = [];
    try {
        const saved = JSON.parse(window.sessionStorage.getItem(storageKey(userId)) ?? "null") as unknown;
        if (Array.isArray(saved)) {
            queue = saved.filter((entry) => !entry?.rejected && typeof entry?.interaction?.interaction_id === "string")
                .map((entry) => entry.interaction);
            if (queue.length < saved.length) save(userId, queue);
        }
    } catch {
        // Storage can be disabled. Pending actions remain available in this tab's memory.
    }
    queues.set(userId, queue);
    return queue;
}

function save(userId: string, queue: Interaction[]): void {
    try {
        if (queue.length) window.sessionStorage.setItem(storageKey(userId), JSON.stringify(queue.map((interaction) => ({ interaction }))));
        else window.sessionStorage.removeItem(storageKey(userId));
    } catch {
        // Sending does not depend on browser storage.
    }
}

function createId(): string | undefined {
    const generator = globalThis.crypto;
    if (!generator) return;
    if (generator.randomUUID) return generator.randomUUID();
    const bytes = generator.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
}

export function recordInteraction(
    userId: string | null,
    itemId: string,
    eventType: InteractionType,
    origin?: InteractionOrigin,
): Interaction | undefined {
    if (!userId) return;
    const interactionId = createId();
    if (!interactionId) return;
    const interaction: Interaction = {
        interaction_id: interactionId,
        item_id: itemId,
        event_type: eventType,
        timestamp: new Date().toISOString(),
        ...origin,
    };
    const queue = queueFor(userId);
    queue.push(interaction);
    save(userId, queue);
    if (active?.userId === userId) active.schedule();
    return interaction;
}

export function startInteractionDelivery(userId: string): () => void {
    const controller = new AbortController();
    let timer: number | undefined;
    let running = false;
    let awaitingAccount = false;
    let retryMs = INITIAL_RETRY_MS;
    const batchToSend = () => queueFor(userId).slice(0, BATCH_SIZE);

    const suspendOnAuthError = (error: unknown): boolean => {
        if (!(error instanceof ApiError) || (error.status !== 401 && error.status !== 403)) return false;
        awaitingAccount = true;
        window.clearTimeout(timer);
        timer = undefined;
        return true;
    };

    const discard = (entries: Interaction[]) => {
        if (!entries.length) return;
        const done = new Set(entries);
        const remaining = queueFor(userId).filter((entry) => !done.has(entry));
        queues.set(userId, remaining);
        save(userId, remaining);
    };

    const acknowledge = (batch: Interaction[], ids: string[]): boolean => {
        const received = new Set(Array.isArray(ids) ? ids : []);
        const accepted = batch.filter((entry) => received.has(entry.interaction_id));
        discard(accepted);
        return accepted.length === batch.length;
    };

    const send = async (batch: Interaction[]): Promise<void> => {
        if (!batch.length || awaitingAccount || controller.signal.aborted) return;
        try {
            const response = await postInteractions(userId, batch, { signal: controller.signal });
            if (!acknowledge(batch, response.accepted_interaction_ids)) throw new Error("Incomplete interaction acknowledgement");
        } catch (error) {
            if (controller.signal.aborted || suspendOnAuthError(error)) return;
            if (!(error instanceof ApiError) || ![400, 409, 413, 422].includes(error.status)) throw error;
            if (batch.length === 1) {
                discard(batch);
                return;
            }
            const middle = Math.ceil(batch.length / 2);
            await send(batch.slice(0, middle));
            await send(batch.slice(middle));
        }
    };

    const schedule = (delay = BATCH_DELAY_MS) => {
        if (controller.signal.aborted || awaitingAccount || running || timer !== undefined || !batchToSend().length) return;
        timer = window.setTimeout(() => {
            timer = undefined;
            void flush();
        }, delay);
    };

    const flush = async () => {
        running = true;
        let delay = BATCH_DELAY_MS;
        try {
            await send(batchToSend());
            retryMs = INITIAL_RETRY_MS;
        } catch {
            delay = retryMs;
            retryMs = Math.min(retryMs * 2, MAX_RETRY_MS);
        } finally {
            running = false;
            schedule(delay);
        }
    };

    const resume = () => {
        awaitingAccount = false;
        window.clearTimeout(timer);
        timer = undefined;
        schedule(0);
    };
    const onFocus = () => {
        if (awaitingAccount) resume();
    };
    const onPageHide = () => {
        if (awaitingAccount) return;
        const batch = batchToSend();
        if (!batch.length) return;
        void postInteractions(userId, batch, { keepalive: true })
            .then((response) => { acknowledge(batch, response.accepted_interaction_ids); })
            .catch(suspendOnAuthError);
    };
    const delivery = { userId, schedule, resume };
    active = delivery;
    window.addEventListener("online", resume);
    window.addEventListener("focus", onFocus);
    window.addEventListener("pagehide", onPageHide);
    schedule();
    return () => {
        controller.abort();
        window.clearTimeout(timer);
        window.removeEventListener("online", resume);
        window.removeEventListener("focus", onFocus);
        window.removeEventListener("pagehide", onPageHide);
        if (active === delivery) active = undefined;
    };
}

export function resumeInteractionDelivery(userId: string): void {
    if (active?.userId === userId) active.resume();
}
