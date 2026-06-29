import Link from "next/link";

import Avatar from "@/components/Avatar";

interface PostCardProps {
    content: string;
    createdAt: string;
    author: {
        id: number;
        username: string | null;
        display_name: string | null;
    };
}

export default function PostCard({ content, createdAt, author }: PostCardProps) {
    const handle = author.username
        ? `@${author.username}`
        : (author.display_name ?? `User ${author.id}`);
    const name = author.display_name ?? handle;

    return (
        <article className="flex gap-3 border-b border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900/40">
            <Avatar name={name} id={author.id} />
            <div className="min-w-0 flex-1">
                <div className="mb-0.5 flex flex-wrap items-center gap-x-2 text-sm">
                    {author.username ? (
                        <Link
                            href={`/u/${author.username}`}
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
                        {new Date(createdAt).toLocaleString()}
                    </time>
                </div>
                <p className="whitespace-pre-wrap break-words">{content}</p>
            </div>
        </article>
    );
}
