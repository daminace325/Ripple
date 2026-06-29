"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, getToken, login } from "@/lib/api";

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (getToken()) router.replace("/");
    }, [router]);

    async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
        e.preventDefault();
        setError(null);
        setLoading(true);
        try {
            await login(email, password);
            router.push("/");
        } catch (err) {
            setError(err instanceof ApiError ? err.message : "Login failed");
        } finally {
            setLoading(false);
        }
    }

    return (
        <main className="flex flex-1 items-center justify-center p-6">
            <form
                onSubmit={onSubmit}
                className="w-full max-w-sm space-y-4 rounded-2xl border border-zinc-200 p-8 dark:border-zinc-800"
            >
                <h1 className="text-2xl font-semibold">Log in to Ripple</h1>

                {error && (
                    <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
                        {error}
                    </p>
                )}

                <label className="block space-y-1">
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                        Email
                    </span>
                    <input
                        type="email"
                        required
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full rounded-lg border border-zinc-300 px-3 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900"
                    />
                </label>

                <label className="block space-y-1">
                    <span className="text-sm text-zinc-600 dark:text-zinc-400">
                        Password
                    </span>
                    <input
                        type="password"
                        required
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full rounded-lg border border-zinc-300 px-3 py-2 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900"
                    />
                </label>

                <button
                    type="submit"
                    disabled={loading}
                    className="w-full rounded-lg bg-zinc-900 px-4 py-2 font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-zinc-200"
                >
                    {loading ? "Logging in…" : "Log in"}
                </button>

                <p className="text-center text-sm text-zinc-600 dark:text-zinc-400">
                    No account?{" "}
                    <Link href="/register" className="font-medium underline">
                        Register
                    </Link>
                </p>
            </form>
        </main>
    );
}
