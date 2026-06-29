import Link from "next/link";

import Avatar from "@/components/Avatar";
import FollowButton from "@/components/FollowButton";
import type { UserCard as UserCardType } from "@/lib/api";

export default function UserCard({ user }: { user: UserCardType }) {
    const handle = user.username ? `@${user.username}` : `User ${user.id}`;
    const name = user.display_name ?? handle;

    return (
        <div className="flex items-center gap-3 border-b border-zinc-200 p-4 transition-colors hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900/40">
            <Avatar name={name} id={user.id} />
            <div className="min-w-0 flex-1">
                {user.username ? (
                    <Link
                        href={`/u/${user.username}`}
                        className="font-semibold hover:underline"
                    >
                        {name}
                    </Link>
                ) : (
                    <span className="font-semibold">{name}</span>
                )}
                <div className="truncate text-sm text-zinc-500">{handle}</div>
            </div>
            <FollowButton
                userId={user.id}
                initialFollowing={user.is_following}
            />
        </div>
    );
}
