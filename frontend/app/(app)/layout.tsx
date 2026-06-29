"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import Sidebar from "@/components/Sidebar";
import { AuthProvider, useAuth } from "@/lib/auth";

function Shell({ children }: { children: React.ReactNode }) {
    const { me, loading } = useAuth();
    const pathname = usePathname();
    const router = useRouter();

    useEffect(() => {
        if (!loading && me && !me.username && pathname !== "/settings") {
            router.replace("/settings");
        }
    }, [loading, me, pathname, router]);

    if (loading || !me) return <div className="p-8 text-zinc-500">Loading…</div>;

    return (
        <div className="mx-auto flex w-full max-w-4xl flex-1">
            <Sidebar />
            <main className="min-h-screen flex-1 border-zinc-200 sm:border-x dark:border-zinc-800">
                <nav className="flex gap-4 border-b border-zinc-200 p-3 text-sm sm:hidden dark:border-zinc-800">
                    <Link href="/">Home</Link>
                    <Link href="/explore">Explore</Link>
                    <Link href={me.username ? `/u/${me.username}` : "/settings"}>
                        Profile
                    </Link>
                    <Link href="/settings">Settings</Link>
                </nav>
                {children}
            </main>
        </div>
    );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
    return (
        <AuthProvider>
            <Shell>{children}</Shell>
        </AuthProvider>
    );
}
