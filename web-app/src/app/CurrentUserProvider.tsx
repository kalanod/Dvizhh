import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getAccount, getUser, logoutAccount } from "../api";
import { CurrentUserContext } from "../hooks";
import type { Profile } from "../models";

export const CurrentUserProvider = ({ children }: { children: ReactNode }) => {
    const [user, setUser] = useState<Profile | null>(null);
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        let cancelled = false;
        getAccount().then((account) => getUser(account.id)).then(
            (profile) => { if (!cancelled) setUser(profile); },
            () => { if (!cancelled) setUser(null); },
        ).finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, []);
    const signIn = useCallback((profile: Profile) => { setUser(profile); }, []);
    const signOut = useCallback(async () => {
        try {
            await logoutAccount();
            setUser(null);
        } catch (error) {
            window.alert(error instanceof ApiError ? error.message : "Не удалось выйти. Попробуйте ещё раз.");
        }
    }, []);
    const updateUser = useCallback((profile: Profile) => {
        setUser((current) => current?.id === profile.id ? profile : current);
    }, []);
    const value = useMemo(() => ({ userId: user?.id ?? null, user, loading, signIn, signOut, updateUser }),
        [user, loading, signIn, signOut, updateUser]);
    return <CurrentUserContext.Provider value={value}>{children}</CurrentUserContext.Provider>;
};
