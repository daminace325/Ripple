async def test_create_post(client, make_user):
    _, headers = await make_user("p@example.com", username="poster")
    r = await client.post("/posts", json={"content": "hello"}, headers=headers)
    assert r.status_code == 201
    assert r.json()["content"] == "hello"


async def test_create_post_empty_422(client, make_user):
    _, headers = await make_user("pe@example.com", username="pempty")
    r = await client.post("/posts", json={"content": ""}, headers=headers)
    assert r.status_code == 422


async def test_create_post_requires_auth(client):
    r = await client.post("/posts", json={"content": "hi"})
    assert r.status_code in (401, 403)


async def test_post_detail(client, make_user):
    _, headers = await make_user("pd@example.com", username="pdetail")
    pid = (
        await client.post("/posts", json={"content": "detail"}, headers=headers)
    ).json()["id"]
    r = await client.get(f"/posts/{pid}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "detail"
    assert body["author"]["username"] == "pdetail"
    assert body["like_count"] == 0
    assert body["liked"] is False
    assert body["comment_count"] == 0


async def test_post_detail_missing_404(client, make_user):
    _, headers = await make_user("pm@example.com", username="pmiss")
    r = await client.get("/posts/999999", headers=headers)
    assert r.status_code == 404


async def test_list_user_posts_newest_first(client, make_user):
    user, headers = await make_user("lp@example.com", username="lister")
    ids = [
        (await client.post("/posts", json={"content": f"p{i}"}, headers=headers)).json()[
            "id"
        ]
        for i in range(3)
    ]
    r = await client.get(f"/users/{user['id']}/posts", headers=headers)
    assert r.status_code == 200
    returned = [p["id"] for p in r.json()]
    assert returned == sorted(ids, reverse=True)


async def test_list_user_posts_missing_user_404(client, make_user):
    _, headers = await make_user("lp2@example.com", username="lp2")
    r = await client.get("/users/999999/posts", headers=headers)
    assert r.status_code == 404


async def test_list_user_posts_cursor_pagination(client, make_user):
    user, headers = await make_user("cur@example.com", username="curuser")
    ids = [
        (await client.post("/posts", json={"content": f"p{i}"}, headers=headers)).json()[
            "id"
        ]
        for i in range(5)
    ]
    newest = sorted(ids, reverse=True)

    r1 = await client.get(
        f"/users/{user['id']}/posts", params={"limit": 2}, headers=headers
    )
    page1 = [p["id"] for p in r1.json()]
    assert page1 == newest[:2]

    r2 = await client.get(
        f"/users/{user['id']}/posts",
        params={"limit": 2, "cursor": page1[-1]},
        headers=headers,
    )
    page2 = [p["id"] for p in r2.json()]
    assert page2 == newest[2:4]
    assert page2[0] < page1[-1]
