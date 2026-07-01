from app.config import settings
from app.services import fanout
from app.services.feed import timeline_key


async def test_create_post_enqueues_fanout_job(client, make_user, redis_conn):
    user, headers = await make_user("eq@example.com", username="enqueuer")
    before = await redis_conn.xlen(fanout.FEED_STREAM)

    r = await client.post("/posts", json={"content": "hello"}, headers=headers)
    pid = r.json()["id"]

    assert await redis_conn.xlen(fanout.FEED_STREAM) == before + 1
    _msg_id, fields = (await redis_conn.xrevrange(fanout.FEED_STREAM, count=1))[0]
    assert int(fields["post_id"]) == pid
    assert int(fields["author_id"]) == user["id"]


async def test_fan_out_pushes_to_materialized_timeline(
    client, make_user, db_session, redis_conn
):
    author, ah = await make_user("fa@example.com", username="fauthor")
    follower, fh = await make_user("fb@example.com", username="ffollower")
    await client.post("/follow", json={"followee_id": author["id"]}, headers=fh)

    # Author's first post + a follower feed read materializes the follower timeline.
    await client.post("/posts", json={"content": "first"}, headers=ah)
    await client.get("/feed", headers=fh)
    assert await redis_conn.exists(timeline_key(follower["id"]))

    # A new post, fanned out by the worker (simulated here), lands in the timeline.
    pid = (await client.post("/posts", json={"content": "second"}, headers=ah)).json()[
        "id"
    ]
    await fanout.fan_out_post(db_session, redis_conn, pid, author["id"])

    members = await redis_conn.zrange(timeline_key(follower["id"]), 0, -1)
    assert str(pid) in members


async def test_fan_out_skips_cold_timeline_but_read_rebuilds(
    client, make_user, db_session, redis_conn
):
    author, ah = await make_user("ca@example.com", username="cauthorx")
    follower, fh = await make_user("cb@example.com", username="cfollower")
    await client.post("/follow", json={"followee_id": author["id"]}, headers=fh)

    # Follower never read their feed → no timeline yet.
    assert not await redis_conn.exists(timeline_key(follower["id"]))

    pid = (await client.post("/posts", json={"content": "hi"}, headers=ah)).json()["id"]
    await fanout.fan_out_post(db_session, redis_conn, pid, author["id"])

    # Cold timeline is not partially created by fan-out …
    assert not await redis_conn.exists(timeline_key(follower["id"]))
    # … but the follower's next feed read rebuilds from Postgres and includes the post.
    feed = (await client.get("/feed", headers=fh)).json()
    assert pid in [item["id"] for item in feed["items"]]


async def test_fan_out_reaches_author_own_timeline(
    client, make_user, db_session, redis_conn
):
    author, ah = await make_user("sa@example.com", username="selfauthor")
    # Materialize the author's own timeline.
    await client.post("/posts", json={"content": "one"}, headers=ah)
    await client.get("/feed", headers=ah)
    assert await redis_conn.exists(timeline_key(author["id"]))

    pid = (await client.post("/posts", json={"content": "two"}, headers=ah)).json()[
        "id"
    ]
    await fanout.fan_out_post(db_session, redis_conn, pid, author["id"])

    members = await redis_conn.zrange(timeline_key(author["id"]), 0, -1)
    assert str(pid) in members


async def test_timeline_trimmed_to_max_size(
    client, make_user, db_session, redis_conn, monkeypatch
):
    monkeypatch.setattr(settings, "timeline_max_size", 3)
    author, ah = await make_user("tr@example.com", username="trimmer")

    # Materialize the author's own timeline, then fan out several posts.
    await client.post("/posts", json={"content": "seed"}, headers=ah)
    await client.get("/feed", headers=ah)

    pids = []
    for i in range(5):
        pid = (
            await client.post("/posts", json={"content": f"p{i}"}, headers=ah)
        ).json()["id"]
        pids.append(pid)
        await fanout.fan_out_post(db_session, redis_conn, pid, author["id"])

    key = timeline_key(author["id"])
    assert await redis_conn.zcard(key) == 3
    kept = sorted(int(m) for m in await redis_conn.zrange(key, 0, -1))
    assert kept == sorted(pids)[-3:]  # newest 3 retained
