// Lightweight typed client for the Ripple API + JWT storage helpers.

const API_BASE =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const TOKEN_KEY = "ripple_token";

export function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
    window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
    window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
        this.name = "ApiError";
    }
}

function extractDetail(data: unknown, status: number): string {
    if (data && typeof data === "object" && "detail" in data) {
        const detail = (data as { detail: unknown }).detail;
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail)) {
            const msgs = detail
                .map((d) =>
                    d && typeof d === "object" && "msg" in d
                        ? String((d as { msg: unknown }).msg)
                        : "",
                )
                .filter(Boolean);
            if (msgs.length) return msgs.join(", ");
        }
    }
    return `Request failed (${status})`;
}

async function request<T>(
    path: string,
    options: RequestInit = {},
    auth = true,
): Promise<T> {
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
    };
    if (options.headers) Object.assign(headers, options.headers);
    if (auth) {
        const token = getToken();
        if (token) headers.Authorization = `Bearer ${token}`;
    }

    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 204) return undefined as T;

    let data: unknown = null;
    try {
        data = await res.json();
    } catch {
        data = null;
    }

    if (!res.ok) {
        if (res.status === 401 && auth) clearToken();
        throw new ApiError(res.status, extractDetail(data, res.status));
    }
    return data as T;
}

// ---- Types ----
export interface Me {
    id: number;
    email: string;
    username: string | null;
    display_name: string | null;
    created_at: string;
}

export interface UserOut {
    id: number;
    username: string | null;
    display_name: string | null;
    created_at: string;
}

export interface UserCard {
    id: number;
    username: string | null;
    display_name: string | null;
    is_following: boolean;
}

export interface UserProfile {
    id: number;
    username: string | null;
    display_name: string | null;
    created_at: string;
    followers_count: number;
    following_count: number;
    is_following: boolean;
}

export interface FeedAuthor {
    id: number;
    username: string | null;
    display_name: string | null;
}

export interface FeedItem {
    id: number;
    content: string;
    created_at: string;
    author: FeedAuthor;
}

export interface FeedPage {
    items: FeedItem[];
    next_cursor: number | null;
}

export interface PostOut {
    id: number;
    author_id: number;
    content: string;
    created_at: string;
}

interface TokenResponse {
    access_token: string;
    token_type: string;
}

// ---- Auth ----
export function register(email: string, password: string): Promise<Me> {
    return request<Me>(
        "/auth/register",
        { method: "POST", body: JSON.stringify({ email, password }) },
        false,
    );
}

export async function login(email: string, password: string): Promise<void> {
    const token = await request<TokenResponse>(
        "/auth/login",
        { method: "POST", body: JSON.stringify({ email, password }) },
        false,
    );
    setToken(token.access_token);
}

export function getMe(): Promise<Me> {
    return request<Me>("/users/me");
}

export function updateProfile(payload: {
    username?: string;
    display_name?: string;
}): Promise<Me> {
    return request<Me>("/users/me", {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
}

// ---- Users / follow ----
export function getProfile(username: string): Promise<UserProfile> {
    return request<UserProfile>(
        `/users/by-username/${encodeURIComponent(username)}`,
    );
}

export function searchUsers(q: string, limit = 20): Promise<UserCard[]> {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    params.set("limit", String(limit));
    return request<UserCard[]>(`/users/search?${params.toString()}`);
}

export function getUserPosts(userId: number, limit = 20): Promise<PostOut[]> {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    return request<PostOut[]>(`/users/${userId}/posts?${params.toString()}`);
}

export function follow(followeeId: number): Promise<unknown> {
    return request("/follow", {
        method: "POST",
        body: JSON.stringify({ followee_id: followeeId }),
    });
}

export function unfollow(followeeId: number): Promise<unknown> {
    return request("/follow", {
        method: "DELETE",
        body: JSON.stringify({ followee_id: followeeId }),
    });
}

// ---- Posts / feed ----
export function createPost(content: string): Promise<PostOut> {
    return request<PostOut>("/posts", {
        method: "POST",
        body: JSON.stringify({ content }),
    });
}

export function getFeed(cursor?: number | null, limit = 20): Promise<FeedPage> {
    const params = new URLSearchParams();
    if (cursor) params.set("cursor", String(cursor));
    params.set("limit", String(limit));
    return request<FeedPage>(`/feed?${params.toString()}`);
}
