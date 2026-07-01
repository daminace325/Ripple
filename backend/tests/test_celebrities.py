from app.config import settings
from app.services import celebrities
from app.services import fanout


async def test_follower_count_backfills_then_increments(
    client, make_user, db_session, redis_conn
):
    target, _ = await make_user("cel@example.com", username="celeb")
    _, h1 = await make_user("f1@example.com", username="follower1")

    # No counter yet → backfilled from Postgres (0).
    assert await celebrities.get_follower_count(redis_conn, db_session, target["id"]) == 0

    # A real follow bumps the maintained counter.
    await client.post("/follow", json={"followee_id": target["id"]}, headers=h1)
    assert await celebrities.get_follower_count(redis_conn, db_session, target["id"]) == 1


async def test_follower_count_backfill_sets_self_healing_ttl(
    client, make_user, db_session, redis_conn
):
    target, _ = await make_user("ttl@example.com", username="ttluser")
    await celebrities.get_follower_count(redis_conn, db_session, target["id"])
    assert await redis_conn.ttl(celebrities.follower_count_key(target["id"])) > 0


async def test_follower_count_clamps_negative(make_user, db_session, redis_conn):
    user, _ = await make_user("neg@example.com", username="neguser")
    await redis_conn.set(celebrities.follower_count_key(user["id"]), -5)
    assert await celebrities.get_follower_count(redis_conn, db_session, user["id"]) == 0


async def test_follower_count_decrements_on_unfollow(
    client, make_user, db_session, redis_conn
):
    target, _ = await make_user("cel2@example.com", username="celeb2")
    _, h1 = await make_user("f2@example.com", username="follower2")

    await client.post("/follow", json={"followee_id": target["id"]}, headers=h1)
    # Materialize the counter (=1), then unfollow.
    assert await celebrities.get_follower_count(redis_conn, db_session, target["id"]) == 1
    await client.request(
        "DELETE", "/follow", json={"followee_id": target["id"]}, headers=h1
    )
    assert await celebrities.get_follower_count(redis_conn, db_session, target["id"]) == 0


async def test_idempotent_follow_does_not_double_count(
    client, make_user, db_session, redis_conn
):
    target, _ = await make_user("cel3@example.com", username="celeb3")
    _, h1 = await make_user("f3@example.com", username="follower3")

    # Materialize counter at 0.
    await celebrities.get_follower_count(redis_conn, db_session, target["id"])
    await client.post("/follow", json={"followee_id": target["id"]}, headers=h1)
    await client.post("/follow", json={"followee_id": target["id"]}, headers=h1)  # dup

    assert await celebrities.get_follower_count(redis_conn, db_session, target["id"]) == 1


async def test_is_celebrity_threshold(
    client, make_user, db_session, redis_conn, monkeypatch
):
    monkeypatch.setattr(settings, "celebrity_threshold", 2)
    target, _ = await make_user("star@example.com", username="star")

    assert not await celebrities.is_celebrity(redis_conn, db_session, target["id"])

    for i in range(2):
        _, h = await make_user(f"cf{i}@example.com", username=f"cfollow{i}")
        await client.post("/follow", json={"followee_id": target["id"]}, headers=h)

    assert await celebrities.is_celebrity(redis_conn, db_session, target["id"])


async def test_celebrity_post_skips_fanout(
    client, make_user, redis_conn, monkeypatch
):
    monkeypatch.setattr(settings, "celebrity_threshold", 1)
    star, sh = await make_user("bigstar@example.com", username="bigstar")
    _, fh = await make_user("fan@example.com", username="fanuser")
    await client.post("/follow", json={"followee_id": star["id"]}, headers=fh)

    # star now has 1 follower ≥ threshold(1) → celebrity → no fan-out job.
    before = await redis_conn.xlen(fanout.FEED_STREAM)
    r = await client.post("/posts", json={"content": "celeb post"}, headers=sh)
    assert r.status_code == 201
    assert await redis_conn.xlen(fanout.FEED_STREAM) == before


async def test_normal_post_still_enqueues(client, make_user, redis_conn, monkeypatch):
    monkeypatch.setattr(settings, "celebrity_threshold", 1)
    _, h = await make_user("normie@example.com", username="normie")

    before = await redis_conn.xlen(fanout.FEED_STREAM)
    await client.post("/posts", json={"content": "hi"}, headers=h)
    assert await redis_conn.xlen(fanout.FEED_STREAM) == before + 1


async def test_celebrity_post_cached(client, make_user, redis_conn, monkeypatch):
    monkeypatch.setattr(settings, "celebrity_threshold", 1)
    star, sh = await make_user("cachestar@example.com", username="cachestar")
    _, fh = await make_user("cfan@example.com", username="cfan")
    await client.post("/follow", json={"followee_id": star["id"]}, headers=fh)

    p1 = (await client.post("/posts", json={"content": "a"}, headers=sh)).json()["id"]
    p2 = (await client.post("/posts", json={"content": "b"}, headers=sh)).json()["id"]

    key = celebrities.recent_posts_key(star["id"])
    assert await redis_conn.zcard(key) == 2
    ids = [int(m) for m in await redis_conn.zrevrange(key, 0, -1)]
    assert ids == [p2, p1]  # newest first


async def test_recent_posts_backfill_on_miss(
    client, make_user, db_session, redis_conn, monkeypatch
):
    # Author posts while "normal"; later classified celebrity with an empty cache.
    author, ah = await make_user("late@example.com", username="latestar")
    pids = [
        (await client.post("/posts", json={"content": f"p{i}"}, headers=ah)).json()[
            "id"
        ]
        for i in range(3)
    ]
    assert not await redis_conn.exists(celebrities.recent_posts_key(author["id"]))

    got = await celebrities.get_recent_post_ids(
        redis_conn, db_session, author["id"], limit=10
    )
    assert got == sorted(pids, reverse=True)
