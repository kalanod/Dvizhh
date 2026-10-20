export type ProfileStatus = "ACTIVE" | "SUSPENDED" | "DELETED";
export type FriendshipStatus = "PENDING" | "ACCEPTED" | "DECLINED" | "REMOVED";

export interface UserSummary {
    id: string;
    username: string;
    display_name: string;
}

/** Профиль в формате ProfileDTO backend-а. */
export interface Profile {
    id: string;
    username: string;
    display_name: string;
    bio: string | null;
    avatar_media_id: string | null;
    city: string | null;
    latitude: string | null;
    longitude: string | null;
    status: ProfileStatus;
    created_at: string;
    updated_at: string;
}

/** Тело POST /api/users. */
export interface CreateUserInput {
    username: string;
    display_name: string;
    bio: string | null;
    city: string | null;
}

export interface Friendship {
    user_low_id: string;
    user_high_id: string;
    requested_by_user_id: string;
    status: FriendshipStatus;
    requested_at: string;
    responded_at: string | null;
    removed_at: string | null;
}
