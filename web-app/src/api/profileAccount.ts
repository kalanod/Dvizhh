import type { UpdateProfileInput } from "../models";
import { getAccount, normalizeUsername, updateAccount } from "./auth";
import { ApiError, errorText } from "./client";
import { updateProfile } from "./personal";

/** Auth owns the login username; retries re-read it before updating the profile mirror. */
export async function saveProfileWithAccount(profileId: string, previousUsername: string, input: UpdateProfileInput & { username: string }, email?: string | null) {
    const username = normalizeUsername(input.username);
    const account = await getAccount();
    if (account.id !== profileId) throw new Error("Аккаунт изменился. Откройте свой профиль заново.");
    const normalizedEmail = email?.trim().toLowerCase() || null;
    const accountPatch = {
        ...(account.username !== username ? { username } : {}),
        ...(email !== undefined && account.email !== normalizedEmail ? { email: normalizedEmail } : {}),
    };
    if (Object.keys(accountPatch).length) await updateAccount(accountPatch);
    try {
        return await updateProfile(profileId, { ...input, username });
    } catch (error) {
        if (username !== previousUsername) {
            if (error instanceof ApiError && error.status === 409) {
                throw new Error(`Никнейм для входа уже изменён на «${username}», но этот никнейм занят в профилях. Выберите другой никнейм и сохраните профиль.`);
            }
            throw new Error(`Никнейм для входа уже изменён на «${username}», но профиль не сохранён. ${errorText(error)} Повторите сохранение.`);
        }
        if (email !== undefined) {
            throw new Error(`Данные аккаунта для входа сохранены, но профиль сохранить не удалось. ${errorText(error)} Повторите сохранение.`);
        }
        throw error;
    }
}
