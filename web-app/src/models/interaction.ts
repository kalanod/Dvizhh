export interface InteractionOrigin {
    session_id: string;
    request_id: string;
}

export type InteractionType = "IMPRESSION" | "OPEN" | "JOIN_CLICK" | "EXTERNAL_LINK_CLICK";

export interface Interaction extends Partial<InteractionOrigin> {
    interaction_id: string;
    item_id: string;
    event_type: InteractionType;
    timestamp: string;
}
