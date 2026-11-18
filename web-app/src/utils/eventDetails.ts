import type { DvizhEvent } from "../models";
import type { InteractionOrigin } from "../models/interaction";

export function eventDetailsPath(event: Pick<DvizhEvent, "id" | "occurrence_id">): string {
    return `/events/${event.id}?${new URLSearchParams({ occurrence_id: event.occurrence_id })}`;
}

export interface EventNavigationState {
    notice?: string;
    attribution?: { userId: string; origin: InteractionOrigin };
}
