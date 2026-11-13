import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { getAccount } from "../api/auth";
import { useAsync } from "./useAsync";
import { useCurrentUser } from "./useCurrentUser";

/** Recheck the server role on navigation and when returning to the application. */
export const useAdminAccess = () => {
    const { userId, loading: sessionLoading } = useCurrentUser();
    const { pathname } = useLocation();
    const state = useAsync(
        (signal) => userId ? getAccount(signal) : Promise.resolve(null),
        `admin-access:${userId}:${pathname}`,
    );
    useEffect(() => {
        window.addEventListener("focus", state.reload);
        return () => window.removeEventListener("focus", state.reload);
    }, [state.reload]);
    const loading = sessionLoading || Boolean(userId && state.loading);
    return {
        allowed: !loading && Boolean(userId && state.data?.id === userId && state.data.role === "admin"),
        loading,
        error: userId ? state.error : undefined,
        reload: state.reload,
    };
};
