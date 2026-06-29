"use client";

import { useState } from "react";

import { follow, unfollow } from "@/lib/api";

export default function FollowButton({
    userId,
    initialFollowing,
    onChange,
}: {
    userId: number;
    initialFollowing: boolean;
    onChange?: (following: boolean) => void;
}) {
    const [following, setFollowing] = useState(initialFollowing);
    const [busy, setBusy] = useState(false);

    async function toggle() {
        setBusy(true);
        const prev = following;
        const next = !prev;
        setFollowing(next);
        onChange?.(next);
        try {
            if (prev) {
                await unfollow(userId);
            } else {
                await follow(userId);
            }
        } catch {
            setFollowing(prev);
            onChange?.(prev);
        } finally {
            setBusy(false);
        }
    }

    return (
        <button
            onClick={toggle}
            disabled={busy}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 ${
                following
                    ? "border border-zinc-300 hover:border-red-300 hover:text-red-600 dark:border-zinc-700"
                    : "bg-zinc-900 text-white dark:bg-white dark:text-black"
            }`}
        >
            {following ? "Following" : "Follow"}
        </button>
    );
}
