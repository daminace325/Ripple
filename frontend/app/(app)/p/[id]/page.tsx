"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import PostCard from "@/components/PostCard";
import { ApiError, getPost, type PostDetail } from "@/lib/api";

export default function PostDetailPage({
    params,
}: {
    params: Promise<{ id: string }>;
}) {
    const { id } = use(params);
    const [post, setPost] = useState<PostDetail | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            setLoading(true);
            setError(null);
            try {
                setPost(await getPost(Number(id)));
            } catch (err) {
                setError(
                    err instanceof ApiError ? err.message : "Could not load post",
                );
            } finally {
                setLoading(false);
            }
        })();
    }, [id]);

    return (
        <div>
            <div className="flex items-center gap-3 border-b border-zinc-200 p-4 dark:border-zinc-800">
                <Link
                    href="/"
                    className="text-xl text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
                    aria-label="Back"
                >
                    ←
                </Link>
                <h1 className="text-xl font-bold">Post</h1>
            </div>
            {loading ? (
                <p className="p-4 text-zinc-500">Loading…</p>
            ) : error || !post ? (
                <p className="p-4 text-zinc-500">{error ?? "Not found"}</p>
            ) : (
                <div className="mx-auto max-w-xl p-4">
                    <div className="overflow-hidden rounded-2xl border border-zinc-200 shadow-sm dark:border-zinc-800">
                        <PostCard
                            content={post.content}
                            createdAt={post.created_at}
                            author={post.author}
                            postId={post.id}
                            likeCount={post.like_count}
                            liked={post.liked}
                            clickable={false}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
