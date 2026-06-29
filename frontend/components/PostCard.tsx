import Link from "next/link";

interface PostCardProps {
    content: string;
    createdAt: string;
    author: {
        id: number;
        username: string | null;
        display_name: string | null;
    };
}

export default function PostCard({
    content,
    createdAt,
    author,
}: PostCardProps) {
    const handle = author.username
        ? `@${author.username}`
        : (author.display_name ?? `User ${author.id}`);

    return (
        <article className="border-b border-zinc-200 p-4 dark:border-zinc-800">
            <div className="mb-1 flex flex-wrap items-center gap-x-2 text-sm">
                {author.username ? (
                    <Link
                        href={`/u/${author.username}`}
                        className="font-semibold hover:underline"
                    >
                        {author.display_name ?? handle}
                    </Link>
                ) : (
                    <span className="font-semibold">
                        {author.display_name ?? handle}
                    </span>
                )}
                <span className="text-zinc-500">{handle}</span>
                <span className="text-zinc-400">·</span>
                <time className="text-zinc-500">
                    {new Date(createdAt).toLocaleString()}
                </time>
            </div>
            <p className="whitespace-pre-wrap">{content}</p>
        </article>
    );
}
