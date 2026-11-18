import type { AccountRole, CurrentAccount } from "./auth";
import { request } from "./client";

export interface AdminUsersPage {
    items: CurrentAccount[];
    offset: number;
    limit: number;
    has_more: boolean;
}

export const searchAdminUsers = (q: string, offset: number, signal?: AbortSignal) =>
    request<AdminUsersPage>("/admin/users", { query: { q: q.trim(), offset, limit: 20 }, signal });

export const changeAdminUserRole = (id: string, role: AccountRole) =>
    request<CurrentAccount>(`/admin/users/${encodeURIComponent(id)}/role`, {
        method: "PATCH", headers: { "X-Dvizh-Admin": "1" }, body: { role },
    });

export const resetAdminUserPassword = (id: string, newPassword: string) =>
    request<void>(`/admin/users/${encodeURIComponent(id)}/password`, {
        method: "POST", headers: { "X-Dvizh-Admin": "1" }, body: { new_password: newPassword },
    });
