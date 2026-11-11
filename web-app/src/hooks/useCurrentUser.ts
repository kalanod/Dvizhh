import { createContext, useContext } from "react";
import type { Profile } from "../models";

export interface CurrentUserValue {
    /** ID профиля текущего аккаунта, полученного через cookie-сессию. */
    userId: string | null;
    user: Profile | null;
    loading: boolean;
    signIn: (profile: Profile) => void;
    updateUser: (profile: Profile) => void;
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
