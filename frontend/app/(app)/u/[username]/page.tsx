"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import FollowButton from "@/components/FollowButton";
import PostCard from "@/components/PostCard";
import Avatar from "@/components/Avatar";
import { useAuth } from "@/lib/auth";
import {
    ApiError,
    getProfile,
    getUserPosts,
    type PostDetail,
    type UserProfile,
} from "@/lib/api";

export default function ProfilePage({
    params,
}: {
    params: Promise<{ username: string }>;
}) {
    const { username } = use(params);
    const { me } = useAuth();
    const [profile, setProfile] = useState<UserProfile | null>(null);
    const [posts, setPosts] = useState<PostDetail[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            setLoading(true);
            setError(null);
            try {
                const p = await getProfile(username);
                setProfile(p);
                setPosts(await getUserPosts(p.id));
            } catch (err) {
                setError(
                    err instanceof ApiError
                        ? err.message
                        : "Could not load profile",
                );
            } finally {
                setLoading(false);
            }
        })();
    }, [username]);

    if (loading) return <p className="p-4 text-zinc-500">Loading…</p>;
    if (error || !profile)
        return <p className="p-4 text-zinc-500">{error ?? "Not found"}</p>;

    const isMe = me?.id === profile.id;
    const handle = profile.username
        ? `@${profile.username}`
        : `User ${profile.id}`;

    return (
        <div>
            <div className="border-b border-zinc-200 p-4 dark:border-zinc-800">
                <div className="flex items-start justify-between gap-4">
                    <div className="flex min-w-0 gap-3">
                        <Avatar
                            name={profile.display_name ?? handle}
                            id={profile.id}
                            size={56}
                        />
                        <div className="min-w-0">
                            <h1 className="truncate text-xl font-bold">
                                {profile.display_name ?? handle}
                            </h1>
                            <p className="text-zinc-500">{handle}</p>
                        </div>
                    </div>
                    {isMe ? (
                        <Link
                            href="/settings"
                            className="shrink-0 rounded-full border border-zinc-300 px-4 py-1.5 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-900"
                        >
                            Edit profile
                        </Link>
                    ) : (
                        <FollowButton
                            userId={profile.id}
                            initialFollowing={profile.is_following}
                        />
                    )}
                </div>
                <div className="mt-3 flex gap-4 text-sm text-zinc-600 dark:text-zinc-400">
                    <span>
                        <b className="text-zinc-900 dark:text-zinc-100">
                            {profile.following_count}
                        </b>{" "}
                        Following
                    </span>
                    <span>
                        <b className="text-zinc-900 dark:text-zinc-100">
                            {profile.followers_count}
                        </b>{" "}
                        Followers
                    </span>
                </div>
            </div>
            {posts.length === 0 ? (
                <p className="p-4 text-zinc-500">No posts yet.</p>
            ) : (
                posts.map((p) => (
                    <PostCard
                        key={p.id}
                        content={p.content}
                        createdAt={p.created_at}
                        author={{
                            id: profile.id,
                            username: profile.username,
                            display_name: profile.display_name,
                        }}
                        postId={p.id}
                        likeCount={p.like_count}
                        liked={p.liked}
                    />
                ))
            )}
        </div>
    );
}
