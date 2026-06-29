"use client";

import { useState } from "react";

import Avatar from "@/components/Avatar";
import { ApiError, createPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function Composer({ onPosted }: { onPosted: () => void }) {
    const { me } = useAuth();
    const [content, setContent] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    async function submit(e: React.FormEvent<HTMLFormElement>) {
        e.preventDefault();
        setError(null);
        setBusy(true);
        try {
            await createPost(content.trim());
            setContent("");
            onPosted();
        } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not post");
        } finally {
            setBusy(false);
        }
    }

    return (
        <form
            onSubmit={submit}
            className="flex gap-3 border-b border-zinc-200 p-4 dark:border-zinc-800"
        >
            <Avatar name={me?.display_name ?? me?.username ?? "?"} id={me?.id ?? 0} />
            <div className="flex-1">
                {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
                <textarea
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="What's happening?"
                    maxLength={280}
                    rows={3}
                    className="w-full resize-none bg-transparent text-lg outline-none"
                />
                <div className="flex items-center justify-between">
                    <span className="text-xs text-zinc-500">
                        {content.length}/280
                    </span>
                    <button
                        type="submit"
                        disabled={busy || content.trim().length === 0}
                        className="rounded-full bg-sky-600 px-5 py-1.5 font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-50"
                    >
                        Post
                    </button>
                </div>
            </div>
        </form>
    );
}
