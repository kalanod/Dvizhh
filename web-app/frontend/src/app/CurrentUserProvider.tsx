import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, getUser } from "../api";
import { CurrentUserContext } from "../hooks";
import type { Profile } from "../models";

const STORAGE_KEY = "dvizh.userId";

const readStoredId = (): string | null => {
    try {
        return localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;
    }
};

const storeId = (userId: string | null) => {
    try {
        if (userId) {
            localStorage.setItem(STORAGE_KEY, userId);
        } else {
            localStorage.removeItem(STORAGE_KEY);
        }
    } catch {
        // Хранилище недоступно (приватный режим) — вход живёт до перезагрузки.
    }
};

/**
 * Текущий пользователь. Пока auth-api не выдаёт токены, «вход» — это выбранный ID профиля,
 * сохранённый в браузере.
 */
export const CurrentUserProvider = ({ children }: { children: ReactNode }) => {
    const [userId, setUserId] = useState<string | null>(readStoredId);
    const [user, setUser] = useState<Profile | null>(null);
    const [failedId, setFailedId] = useState<string | null>(null);

    useEffect(() => {
        if (!userId || user?.id === userId || failedId === userId) {
            return;
        }
        let cancelled = false;
        getUser(userId).then(
            (profile) => !cancelled && setUser(profile),
            (error: unknown) => {
                if (cancelled) return;
                if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
                    storeId(null);
                    setUserId(null);
                } else {
                    setFailedId(userId);
                }
            },
        );
        return () => {
            cancelled = true;
        };
    }, [userId, user, failedId]);

    const signIn = useCallback((profile: Profile) => {
        storeId(profile.id);
        setUserId(profile.id);
        setUser(profile);
    }, []);

    const signOut = useCallback(() => {
        storeId(null);
        setUserId(null);
        setUser(null);
    }, []);

    const value = useMemo(() => {
        const currentUser = user?.id === userId ? user : null;
        return {
            userId,
            user: currentUser,
            loading: userId !== null && currentUser === null && failedId !== userId,
            signIn,
            signOut,
        };
    }, [userId, user, failedId, signIn, signOut]);

    return <CurrentUserContext.Provider value={value}>{children}</CurrentUserContext.Provider>;
};
