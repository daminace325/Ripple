async def test_add_and_list_comments(client, make_user):
    _, ah = await make_user("cauthor@example.com", username="cauthor")
    _, ch = await make_user("commenter@example.com", username="commenter")
    pid = (await client.post("/posts", json={"content": "post"}, headers=ah)).json()[
        "id"
    ]

    r = await client.post(
        f"/posts/{pid}/comments", json={"content": "nice!"}, headers=ch
    )
    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "nice!"
    assert body["author"]["username"] == "commenter"

    r = await client.get(f"/posts/{pid}/comments", headers=ah)
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_comment_count_in_detail(client, make_user):
    _, headers = await make_user("cc@example.com", username="ccount")
    pid = (await client.post("/posts", json={"content": "p"}, headers=headers)).json()[
        "id"
    ]
    await client.post(f"/posts/{pid}/comments", json={"content": "a"}, headers=headers)
    await client.post(f"/posts/{pid}/comments", json={"content": "b"}, headers=headers)
    d = await client.get(f"/posts/{pid}", headers=headers)
    assert d.json()["comment_count"] == 2


async def test_comment_missing_post_404(client, make_user):
    _, headers = await make_user("cm@example.com", username="cmiss")
    r = await client.post(
        "/posts/999999/comments", json={"content": "x"}, headers=headers
    )
    assert r.status_code == 404


async def test_comment_empty_422(client, make_user):
    _, headers = await make_user("ce@example.com", username="cempty")
    pid = (await client.post("/posts", json={"content": "p"}, headers=headers)).json()[
        "id"
    ]
    r = await client.post(f"/posts/{pid}/comments", json={"content": ""}, headers=headers)
    assert r.status_code == 422


async def test_comments_respects_limit(client, make_user):
    _, headers = await make_user("cl@example.com", username="climit")
    pid = (await client.post("/posts", json={"content": "p"}, headers=headers)).json()[
        "id"
    ]
    for i in range(3):
        await client.post(
            f"/posts/{pid}/comments", json={"content": f"c{i}"}, headers=headers
        )
    r = await client.get(f"/posts/{pid}/comments", params={"limit": 2}, headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 2
