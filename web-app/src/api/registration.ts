import type { CreateUserInput } from "../models";
import { getAccount, loginAccount, normalizeUsername, registerAccount, type RegisterCredentials } from "./auth";
import { ApiError } from "./client";
import { createUser, getUser } from "./users";

/** Retry a partially created registration only after proving ownership of that username. */
export async function registerProfile(credentials: RegisterCredentials, details: Omit<CreateUserInput, "id" | "username">) {
    const username = normalizeUsername(credentials.username);
    let conflict: ApiError | undefined;
    try {
        await registerAccount({ ...credentials, username });
    } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) throw error;
        conflict = error;
    }
    try {
        await loginAccount({ login: username, password: credentials.password });
    } catch (error) {
        throw conflict ?? error;
    }
    const account = await getAccount();
    if (account.username !== username) throw new Error("Не удалось подтвердить никнейм аккаунта. Войдите заново.");
    try {
        return await getUser(account.id);
    } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 404) throw error;
        return createUser({ ...details, id: account.id, username: account.username });
    }
}
