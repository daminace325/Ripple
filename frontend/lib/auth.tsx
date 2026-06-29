"use client";

import { useRouter } from "next/navigation";
import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useState,
} from "react";

import { clearToken, getMe, getToken, type Me } from "@/lib/api";

interface AuthState {
    me: Me | null;
    loading: boolean;
    refresh: () => Promise<void>;
    logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const router = useRouter();
    const [me, setMe] = useState<Me | null>(null);
    const [loading, setLoading] = useState(true);

    const refresh = useCallback(async () => {
        setMe(await getMe());
    }, []);

    const logout = useCallback(() => {
        clearToken();
        setMe(null);
        router.replace("/login");
    }, [router]);

    useEffect(() => {
        if (!getToken()) {
            router.replace("/login");
            return;
        }
        (async () => {
            try {
                await refresh();
            } catch {
                clearToken();
                router.replace("/login");
            } finally {
                setLoading(false);
            }
        })();
    }, [router, refresh]);

    return (
        <AuthContext.Provider value={{ me, loading, refresh, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth(): AuthState {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
