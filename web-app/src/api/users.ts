import { request } from "./client";
import type { CreateUserInput, DvizhEvent, Friendship, Profile } from "../models";

export const createUser = (body: CreateUserInput) => request<Profile>("/users", { method: "POST", body });

export const getUser = (userId: string) => request<Profile>(`/users/${userId}`);

export const getCalendar = (userId: string) => request<DvizhEvent[]>(`/users/${userId}/calendar`);

export const listFriends = (userId: string) => request<Profile[]>(`/users/${userId}/friends`);

export const requestFriendship = (userId: string, friendId: string) =>
    request<Friendship>(`/users/${userId}/friends/${friendId}`, { method: "PUT" });

export const respondToFriendship = (userId: string, friendId: string, accept: boolean) =>
    request<Friendship>(`/users/${userId}/friends/${friendId}`, { method: "PATCH", body: { accept } });

export const removeFriend = (userId: string, friendId: string) =>
    request<void>(`/users/${userId}/friends/${friendId}`, { method: "DELETE" });
