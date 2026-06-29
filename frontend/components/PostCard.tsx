"use client";

import Link from "next/link";

import Avatar from "@/components/Avatar";
import LikeButton from "@/components/LikeButton";

interface PostCardProps {
    content: string;
    createdAt: string;
    author: {
        id: number;
        username: string | null;
        display_name: string | null;
    };
    postId?: number;
    likeCount?: number;
    liked?: boolean;
    clickable?: boolean;
}

export default function PostCard({
    content,
    createdAt,
    author,
    postId,
    likeCount,
    liked,
    clickable = true,
}: PostCardProps) {
    const handle = author.username
        ? `@${author.username}`
        : (author.display_name ?? `User ${author.id}`);
    const name = author.display_name ?? handle;
    const canNav = clickable && postId != null;

    return (
        <article
            className={`relative flex gap-3 border-b border-zinc-200 p-4 transition-colors dark:border-zinc-800 ${
                canNav
                    ? "hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                    : ""
            }`}
        >
            {canNav && (
                <Link
                    href={`/p/${postId}`}
                    aria-label="Open post"
                    className="absolute inset-0 z-0"
                />
            )}
            <Avatar name={name} id={author.id} />
            <div className="min-w-0 flex-1">
                <div className="mb-0.5 flex flex-wrap items-center gap-x-2 text-sm">
                    {author.username ? (
                        <Link
                            href={`/u/${author.username}`}
                            className="relative z-10 font-semibold hover:underline"
                        >
                            {name}
                        </Link>
                    ) : (
                        <span className="font-semibold">{name}</span>
                    )}
                    <span className="text-zinc-500">{handle}</span>
                    <span className="text-zinc-400">·</span>
                    <time className="text-zinc-500">
                        {new Date(createdAt).toLocaleString()}
                    </time>
                </div>
                <p className="whitespace-pre-wrap break-words">{content}</p>
                {postId != null && (
                    <div className="relative z-10 mt-2 w-fit">
                        <LikeButton
                            postId={postId}
                            initialLiked={liked ?? false}
                            initialCount={likeCount ?? 0}
                        />
                    </div>
                )}
            </div>
        </article>
    );
}
