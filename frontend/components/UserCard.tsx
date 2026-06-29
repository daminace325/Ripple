import Link from "next/link";

import FollowButton from "@/components/FollowButton";
import type { UserCard as UserCardType } from "@/lib/api";

export default function UserCard({ user }: { user: UserCardType }) {
    const handle = user.username ? `@${user.username}` : `User ${user.id}`;

    return (
        <div className="flex items-center justify-between border-b border-zinc-200 p-4 dark:border-zinc-800">
            <div className="min-w-0">
                {user.username ? (
                    <Link
                        href={`/u/${user.username}`}
                        className="font-semibold hover:underline"
                    >
                        {user.display_name ?? handle}
                    </Link>
                ) : (
                    <span className="font-semibold">
                        {user.display_name ?? handle}
                    </span>
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
