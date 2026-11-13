import { request } from "./client";

export interface RegisterCredentials { username: string; email?: string | null; password: string }
export interface LoginCredentials { login: string; password: string }
export interface Account { id: string; username: string; email: string | null }
export type AccountRole = "user" | "admin";
export interface CurrentAccount extends Account { role: AccountRole }
export interface UpdateAccountInput { username?: string; email?: string | null }

export const normalizeUsername = (username: string) => username.trim().toLowerCase();
const normalizeEmail = (email?: string | null) => email?.trim().toLowerCase() || null;

export const registerAccount = (body: RegisterCredentials) => request<Account>("/auth/register", {
    method: "POST",
    body: { ...body, username: normalizeUsername(body.username), email: normalizeEmail(body.email) },
});
export const loginAccount = (body: LoginCredentials) => request<void>("/auth/login", {
    method: "POST", body: { ...body, login: body.login.trim().toLowerCase() },
});
export const getAccount = (signal?: AbortSignal) => request<CurrentAccount>("/auth/me", { signal });
export const updateAccount = (body: UpdateAccountInput) => request<CurrentAccount>("/auth/me", {
    method: "PATCH",
    headers: { "X-Dvizh-Account": "1" },
    body: {
        ...body,
        ...(body.username !== undefined ? { username: normalizeUsername(body.username) } : {}),
        ...(body.email !== undefined ? { email: normalizeEmail(body.email) } : {}),
    },
});
export const logoutAccount = () => request<void>("/auth/logout", { method: "POST" });
