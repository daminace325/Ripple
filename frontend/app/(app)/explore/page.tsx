"use client";

import { useEffect, useState } from "react";

import UserCard from "@/components/UserCard";
import { searchUsers, type UserCard as UserCardType } from "@/lib/api";

export default function ExplorePage() {
    const [q, setQ] = useState("");
    const [users, setUsers] = useState<UserCardType[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const timer = setTimeout(async () => {
            setLoading(true);
            try {
                setUsers(await searchUsers(q.trim()));
            } finally {
                setLoading(false);
            }
        }, 250);
        return () => clearTimeout(timer);
    }, [q]);

    return (
        <div>
            <h1 className="border-b border-zinc-200 p-4 text-xl font-bold dark:border-zinc-800">
                Explore
            </h1>
            <div className="border-b border-zinc-200 p-4 dark:border-zinc-800">
                <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Search people by name or @username…"
                    className="w-full rounded-full border border-zinc-300 px-4 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900"
                />
            </div>
            {loading ? (
                <p className="p-4 text-zinc-500">Searching…</p>
            ) : users.length === 0 ? (
                <p className="p-4 text-zinc-500">No users found.</p>
            ) : (
                users.map((u) => <UserCard key={u.id} user={u} />)
            )}
        </div>
    );
}
