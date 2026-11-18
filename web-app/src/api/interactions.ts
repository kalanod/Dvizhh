import type { Interaction } from "../models/interaction";
import { accountWriteHeaders, request } from "./client";

export const postInteractions = (
    userId: string,
    interactions: Interaction[],
    options: { signal?: AbortSignal; keepalive?: boolean } = {},
) => request<{ accepted_interaction_ids: string[] }>("/interactions", {
    method: "POST",
    body: { interactions },
    headers: { ...accountWriteHeaders, "X-Dvizh-Account-Id": userId },
    ...options,
});
