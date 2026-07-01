async def test_feed_shows_own_and_followed_excludes_others(client, make_user):
    _, ah = await make_user("alice@example.com", username="alice")
    bob, bh = await make_user("bob@example.com", username="bob")
    _, ch = await make_user("carol@example.com", username="carol")

    # alice follows bob but not carol
    await client.post("/follow", json={"followee_id": bob["id"]}, headers=ah)

    own = (await client.post("/posts", json={"content": "alice-own"}, headers=ah)).json()[
        "id"
    ]
    bob_post = (
        await client.post("/posts", json={"content": "bob-post"}, headers=bh)
    ).json()["id"]
    carol_post = (
        await client.post("/posts", json={"content": "carol-post"}, headers=ch)
    ).json()["id"]

    r = await client.get("/feed", headers=ah)
    assert r.status_code == 200
    ids = [it["id"] for it in r.json()["items"]]
    assert own in ids
    assert bob_post in ids
    assert carol_post not in ids


async def test_feed_pagination(client, make_user):
    _, headers = await make_user("pag@example.com", username="pag")
    ids = [
        (await client.post("/posts", json={"content": f"n{i}"}, headers=headers)).json()[
            "id"
        ]
        for i in range(5)
    ]

    r = await client.get("/feed", params={"limit": 2}, headers=headers)
    body = r.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    assert body["items"][0]["id"] == max(ids)  # newest first

    r2 = await client.get(
        "/feed", params={"limit": 2, "cursor": body["next_cursor"]}, headers=headers
    )
    body2 = r2.json()
    assert len(body2["items"]) == 2
    assert body2["items"][0]["id"] < body["items"][-1]["id"]


async def test_feed_requires_auth(client):
    r = await client.get("/feed")
    assert r.status_code in (401, 403)


async def test_feed_merges_normal_and_celebrity(client, make_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "celebrity_threshold", 2)
    _, vh = await make_user("viewer2@example.com", username="viewer2")
    normal, nh = await make_user("norm2@example.com", username="normal2")
    star, sh = await make_user("star2@example.com", username="startwo")
    _, eh = await make_user("extra2@example.com", username="extra2")

    # star: 2 followers → celebrity; normal: 1 follower → not.
    await client.post("/follow", json={"followee_id": star["id"]}, headers=vh)
    await client.post("/follow", json={"followee_id": star["id"]}, headers=eh)
    await client.post("/follow", json={"followee_id": normal["id"]}, headers=vh)

    normal_post = (
        await client.post("/posts", json={"content": "from normal"}, headers=nh)
    ).json()["id"]
    celeb_post = (
        await client.post("/posts", json={"content": "from celeb"}, headers=sh)
    ).json()["id"]

    body = (await client.get("/feed", headers=vh)).json()
    ids = [it["id"] for it in body["items"]]
    assert normal_post in ids  # via timeline (rebuild)
    assert celeb_post in ids  # via read-time merge
    assert ids[0] == celeb_post  # newest first


async def test_feed_celebrity_sees_own_post_via_merge(client, make_user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "celebrity_threshold", 1)
    star, sh = await make_user("ownceleb@example.com", username="ownceleb")
    _, fh = await make_user("f@example.com", username="ownfan")
    await client.post("/follow", json={"followee_id": star["id"]}, headers=fh)

    # Materialize the timeline first (no fan-out of celebrity posts into it).
    await client.post("/posts", json={"content": "seed"}, headers=sh)
    await client.get("/feed", headers=sh)

    own_post = (
        await client.post("/posts", json={"content": "mine"}, headers=sh)
    ).json()["id"]

    body = (await client.get("/feed", headers=sh)).json()
    assert own_post in [it["id"] for it in body["items"]]


async def test_feed_hydration_populates_post_cache(client, make_user, redis_conn):
    from app.services.feed import post_cache_key

    _, h = await make_user("hy@example.com", username="hyuser")
    pid = (
        await client.post("/posts", json={"content": "cached body"}, headers=h)
    ).json()["id"]

    # Cache-aside: not cached at creation, populated by the first feed hydration.
    assert not await redis_conn.exists(post_cache_key(pid))
    body = (await client.get("/feed", headers=h)).json()
    assert any(
        it["id"] == pid and it["content"] == "cached body" for it in body["items"]
    )
    assert await redis_conn.exists(post_cache_key(pid))
