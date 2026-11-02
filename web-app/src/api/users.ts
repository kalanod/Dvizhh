import { request } from "./client";
import type { CreateUserInput, DvizhEvent, Friendship, Profile } from "../models";

export const createUser = (body: CreateUserInput) => request<Profile>("/users", { method: "POST", body });

export const getUser = (userId: string, signal?: AbortSignal) => request<Profile>(`/users/${userId}`, { signal });

export const getCalendar = (userId: string, signal?: AbortSignal) =>
    request<DvizhEvent[]>(`/users/${userId}/calendar`, { signal });

export const listFriends = (userId: string, signal?: AbortSignal) =>
    request<Profile[]>(`/users/${userId}/friends`, { signal });

export const requestFriendship = (userId: string, friendId: string) =>
    request<Friendship>(`/users/${userId}/friends/${friendId}`, { method: "PUT" });

export const respondToFriendship = (userId: string, friendId: string, accept: boolean) =>
    request<Friendship>(`/users/${userId}/friends/${friendId}`, { method: "PATCH", body: { accept } });

export const removeFriend = (userId: string, friendId: string) =>
    request<void>(`/users/${userId}/friends/${friendId}`, { method: "DELETE" });
