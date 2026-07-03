async def test_like_and_unlike(client, make_user):
    _, headers = await make_user("lk@example.com", username="lkone")
    pid = (await client.post("/posts", json={"content": "x"}, headers=headers)).json()[
        "id"
    ]

    r = await client.post(f"/posts/{pid}/like", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"post_id": pid, "liked": True, "like_count": 1}

    d = await client.get(f"/posts/{pid}", headers=headers)
    assert d.json()["liked"] is True
    assert d.json()["like_count"] == 1

    r = await client.delete(f"/posts/{pid}/like", headers=headers)
    assert r.status_code == 200
    assert r.json()["liked"] is False
    assert r.json()["like_count"] == 0


async def test_like_idempotent(client, make_user):
    _, headers = await make_user("lk2@example.com", username="lk2")
    pid = (await client.post("/posts", json={"content": "y"}, headers=headers)).json()[
        "id"
    ]
    await client.post(f"/posts/{pid}/like", headers=headers)
    r = await client.post(f"/posts/{pid}/like", headers=headers)
    assert r.json()["like_count"] == 1


async def test_like_missing_post_404(client, make_user):
    _, headers = await make_user("lk3@example.com", username="lk3")
    r = await client.post("/posts/999999/like", headers=headers)
    assert r.status_code == 404


async def test_unlike_missing_post_404(client, make_user):
    _, headers = await make_user("lk4@example.com", username="lk4")
    r = await client.delete("/posts/999999/like", headers=headers)
    assert r.status_code == 404


async def test_like_count_reflects_multiple_users(client, make_user):
    author, ah = await make_user("author@example.com", username="author")
    _, bh = await make_user("liker@example.com", username="liker")
    pid = (await client.post("/posts", json={"content": "z"}, headers=ah)).json()["id"]

    await client.post(f"/posts/{pid}/like", headers=ah)
    await client.post(f"/posts/{pid}/like", headers=bh)

    d = await client.get(f"/posts/{pid}", headers=ah)
    assert d.json()["like_count"] == 2


async def test_like_count_backed_by_redis_counter(client, make_user, redis_conn):
    from app.services.likes import like_count_key

    _, headers = await make_user("lkr@example.com", username="lkredis")
    pid = (
        await client.post("/posts", json={"content": "r"}, headers=headers)
    ).json()["id"]

    # Liking materializes the Redis counter (backfilled from Postgres in the response).
    await client.post(f"/posts/{pid}/like", headers=headers)
    assert await redis_conn.get(like_count_key(pid)) == "1"

    # Unliking decrements the same counter in place.
    await client.delete(f"/posts/{pid}/like", headers=headers)
    assert await redis_conn.get(like_count_key(pid)) == "0"
