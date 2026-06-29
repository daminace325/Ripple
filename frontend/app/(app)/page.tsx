"use client";

import { useCallback, useEffect, useState } from "react";

import Composer from "@/components/Composer";
import PostCard from "@/components/PostCard";
import { ApiError, getFeed, type FeedItem } from "@/lib/api";

export default function HomePage() {
    const [items, setItems] = useState<FeedItem[]>([]);
    const [nextCursor, setNextCursor] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            const page = await getFeed();
            setItems(page.items);
            setNextCursor(page.next_cursor);
        } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not load feed");
        }
    }, []);

    useEffect(() => {
        load().finally(() => setLoading(false));
    }, [load]);

    async function loadMore() {
        if (!nextCursor) return;
        try {
            const page = await getFeed(nextCursor);
            setItems((prev) => [...prev, ...page.items]);
            setNextCursor(page.next_cursor);
        } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not load more");
        }
    }

    return (
        <div>
            <h1 className="border-b border-zinc-200 p-4 text-xl font-bold dark:border-zinc-800">
                Home
            </h1>
            <Composer onPosted={load} />
            {error && <p className="p-4 text-sm text-red-600">{error}</p>}
            {loading ? (
                <p className="p-4 text-zinc-500">Loading…</p>
            ) : items.length === 0 ? (
                <p className="p-4 text-zinc-500">
                    Your feed is empty. Post something or follow people from
                    Explore.
                </p>
            ) : (
                items.map((it) => (
                    <PostCard
                        key={it.id}
                        content={it.content}
                        createdAt={it.created_at}
                        author={it.author}
                        postId={it.id}
                        likeCount={it.like_count}
                        liked={it.liked}
                        commentCount={it.comment_count}
                    />
                ))
            )}
            {nextCursor && (
                <div className="p-4 text-center">
                    <button
                        onClick={loadMore}
                        className="rounded-full border border-zinc-300 px-4 py-2 hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                    >
                        Load more
                    </button>
                </div>
            )}
        </div>
    );
}
