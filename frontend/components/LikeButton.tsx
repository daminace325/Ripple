"use client";

import { useState } from "react";

import { likePost, unlikePost } from "@/lib/api";

export default function LikeButton({
    postId,
    initialLiked,
    initialCount,
}: {
    postId: number;
    initialLiked: boolean;
    initialCount: number;
}) {
    const [liked, setLiked] = useState(initialLiked);
    const [count, setCount] = useState(initialCount);
    const [busy, setBusy] = useState(false);

    async function toggle() {
        if (busy) return;
        setBusy(true);
        const wasLiked = liked;
        setLiked(!wasLiked);
        setCount((c) => c + (wasLiked ? -1 : 1));
        try {
            const r = wasLiked
                ? await unlikePost(postId)
                : await likePost(postId);
            setLiked(r.liked);
            setCount(r.like_count);
        } catch {
            setLiked(wasLiked);
            setCount((c) => c + (wasLiked ? 1 : -1));
        } finally {
            setBusy(false);
        }
    }

    return (
        <button
            onClick={toggle}
            disabled={busy}
            aria-pressed={liked}
            className={`group mt-2 inline-flex items-center gap-1.5 text-sm transition-colors disabled:opacity-60 ${
                liked
                    ? "text-rose-600"
                    : "text-zinc-500 hover:text-rose-600"
            }`}
        >
            <svg
                viewBox="0 0 24 24"
                className="h-5 w-5"
                fill={liked ? "currentColor" : "none"}
                stroke="currentColor"
                strokeWidth={2}
            >
                <path d="M12 21s-7.5-4.7-10-9.3C.7 9 1.4 5.6 4.3 4.3 6.5 3.3 9 4 12 7c3-3 5.5-3.7 7.7-2.7 2.9 1.3 3.6 4.7 2.3 7.4C19.5 16.3 12 21 12 21z" />
            </svg>
            <span className="tabular-nums">{count}</span>
        </button>
    );
}
