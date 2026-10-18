import { createContext, useContext } from "react";
import type { Profile } from "../models";

export interface CurrentUserValue {
    /** ID профиля, под которым выполнен вход (пока нет авторизации, хранится в браузере). */
    userId: string | null;
    user: Profile | null;
    loading: boolean;
    signIn: (profile: Profile) => void;
    signOut: () => void;
}

export const CurrentUserContext = createContext<CurrentUserValue | null>(null);

export const useCurrentUser = (): CurrentUserValue => {
    const value = useContext(CurrentUserContext);
    if (!value) {
        throw new Error("useCurrentUser должен вызываться внутри CurrentUserProvider");
    }
    return value;
};
