"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import Avatar from "@/components/Avatar";
import PostCard from "@/components/PostCard";
import {
    ApiError,
    addComment,
    getComments,
    getPost,
    type CommentOut,
    type PostDetail,
} from "@/lib/api";

export default function PostDetailPage({
    params,
}: {
    params: Promise<{ id: string }>;
}) {
    const { id } = use(params);
    const postId = Number(id);
    const [post, setPost] = useState<PostDetail | null>(null);
    const [comments, setComments] = useState<CommentOut[]>([]);
    const [text, setText] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            setLoading(true);
            setError(null);
            try {
                const [p, c] = await Promise.all([
                    getPost(postId),
                    getComments(postId),
                ]);
                setPost(p);
                setComments(c);
            } catch (err) {
                setError(
                    err instanceof ApiError ? err.message : "Could not load post",
                );
            } finally {
                setLoading(false);
            }
        })();
    }, [postId]);

    async function submit(e: React.FormEvent<HTMLFormElement>) {
        e.preventDefault();
        const content = text.trim();
        if (!content || busy) return;
        setBusy(true);
        try {
            const c = await addComment(postId, content);
            setComments((prev) => [...prev, c]);
            setText("");
        } catch (err) {
            setError(err instanceof ApiError ? err.message : "Could not comment");
        } finally {
            setBusy(false);
        }
    }

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
                            commentCount={comments.length}
                            clickable={false}
                        />
                    </div>

                    <form onSubmit={submit} className="mt-4 flex gap-2">
                        <input
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            placeholder="Post your reply"
                            maxLength={280}
                            className="flex-1 rounded-full border border-zinc-300 bg-transparent px-4 py-2 outline-none focus:border-sky-500 dark:border-zinc-700"
                        />
                        <button
                            type="submit"
                            disabled={busy || text.trim().length === 0}
                            className="rounded-full bg-sky-600 px-5 py-2 font-medium text-white transition-colors hover:bg-sky-500 disabled:opacity-50"
                        >
                            Reply
                        </button>
                    </form>

                    <div className="mt-4 space-y-3">
                        {comments.length === 0 ? (
                            <p className="text-sm text-zinc-500">No comments yet.</p>
                        ) : (
                            comments.map((c) => {
                                const handle = c.author.username
                                    ? `@${c.author.username}`
                                    : (c.author.display_name ?? `User ${c.author.id}`);
                                const name = c.author.display_name ?? handle;
                                return (
                                    <div key={c.id} className="flex gap-3">
                                        <Avatar name={name} id={c.author.id} />
                                        <div className="min-w-0 flex-1">
                                            <div className="flex flex-wrap items-center gap-x-2 text-sm">
                                                {c.author.username ? (
                                                    <Link
                                                        href={`/u/${c.author.username}`}
                                                        className="font-semibold hover:underline"
                                                    >
                                                        {name}
                                                    </Link>
                                                ) : (
                                                    <span className="font-semibold">{name}</span>
                                                )}
                                                <span className="text-zinc-500">{handle}</span>
                                                <span className="text-zinc-400">·</span>
                                                <time className="text-zinc-500">
                                                    {new Date(c.created_at).toLocaleString()}
                                                </time>
                                            </div>
                                            <p className="whitespace-pre-wrap break-words">
                                                {c.content}
                                            </p>
                                        </div>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
