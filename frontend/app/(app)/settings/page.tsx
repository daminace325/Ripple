"use client";

import { useState } from "react";

import { useAuth } from "@/lib/auth";
import { ApiError, updateProfile } from "@/lib/api";

export default function SettingsPage() {
    const { me, refresh } = useAuth();
    const [username, setUsername] = useState(me?.username ?? "");
    const [displayName, setDisplayName] = useState(me?.display_name ?? "");
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    async function submit(e: React.FormEvent<HTMLFormElement>) {
        e.preventDefault();
        setError(null);
        setNotice(null);
        setBusy(true);
        try {
            await updateProfile({
                username: username.trim() || undefined,
                display_name: displayName.trim() || undefined,
            });
            await refresh();
            setNotice("Profile updated.");
        } catch (err) {
            setError(
                err instanceof ApiError ? err.message : "Could not update",
            );
        } finally {
            setBusy(false);
        }
    }

    return (
        <div>
            <h1 className="border-b border-zinc-200 p-4 text-xl font-bold dark:border-zinc-800">
                Settings
            </h1>
            <form onSubmit={submit} className="space-y-4 p-4">
                {!me?.username && (
                    <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
                        Pick a username to start using Ripple.
                    </p>
                )}
                {error && (
                    <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                        {error}
                    </p>
                )}
                {notice && (
                    <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700 dark:bg-green-950 dark:text-green-300">
                        {notice}
                    </p>
                )}
                <label className="block space-y-1">
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                        Username
                    </span>
                    <input
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        minLength={3}
                        className="w-full rounded-lg border border-zinc-300 px-3 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900"
                    />
                </label>
                <label className="block space-y-1">
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                        Display name
                    </span>
                    <input
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        className="w-full rounded-lg border border-zinc-300 px-3 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900"
                    />
                </label>
                <button
                    type="submit"
                    disabled={busy}
                    className="rounded-full bg-zinc-900 px-5 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
                >
                    Save
                </button>
            </form>
        </div>
    );
}
