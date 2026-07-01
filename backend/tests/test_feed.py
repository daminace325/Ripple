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
