import { request } from "./client";

export interface Credentials { email: string; password: string }
export interface Account { id: string; email: string }
export const registerAccount = (body: Credentials) => request<Account>("/auth/register", { method: "POST", body });
export const loginAccount = (body: Credentials) => request<void>("/auth/login", { method: "POST", body });
export const getAccount = () => request<Account>("/auth/me");
export const logoutAccount = () => request<void>("/auth/logout", { method: "POST" });
