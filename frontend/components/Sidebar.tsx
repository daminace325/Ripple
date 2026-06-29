"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";

function NavLink({
    href,
    label,
    active,
}: {
    href: string;
    label: string;
    active: boolean;
}) {
    return (
        <Link
            href={href}
            className={`block rounded-full px-4 py-2 text-lg transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-900 ${
                active ? "font-bold" : ""
            }`}
        >
            {label}
        </Link>
    );
}

export default function Sidebar() {
    const { me, logout } = useAuth();
    const pathname = usePathname();
    const profileHref = me?.username ? `/u/${me.username}` : "/settings";

    return (
        <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col justify-between p-3 sm:flex">
            <div className="space-y-1">
                <div className="mb-4 px-4 text-2xl font-bold">Ripple</div>
                <NavLink href="/" label="Home" active={pathname === "/"} />
                <NavLink
                    href="/explore"
                    label="Explore"
                    active={pathname.startsWith("/explore")}
                />
                <NavLink
                    href={profileHref}
                    label="Profile"
                    active={pathname.startsWith("/u/")}
                />
                <NavLink
                    href="/settings"
                    label="Settings"
                    active={pathname.startsWith("/settings")}
                />
            </div>
            <div className="space-y-2 px-2">
                <div className="truncate px-2 text-sm text-zinc-500">
                    {me?.username ? `@${me.username}` : me?.email}
                </div>
                <button
                    onClick={logout}
                    className="w-full rounded-full border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                >
                    Log out
                </button>
            </div>
        </aside>
    );
}
