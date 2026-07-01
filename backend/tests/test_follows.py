async def test_follow_and_unfollow(client, make_user):
    target, _ = await make_user("t@example.com", username="tee")
    _, headers = await make_user("a@example.com", username="actor")

    r = await client.post("/follow", json={"followee_id": target["id"]}, headers=headers)
    assert r.status_code == 200
    assert r.json()["following"] is True

    r = await client.request(
        "DELETE", "/follow", json={"followee_id": target["id"]}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["following"] is False


async def test_follow_self_400(client, make_user):
    me, headers = await make_user("self@example.com", username="self")
    r = await client.post("/follow", json={"followee_id": me["id"]}, headers=headers)
    assert r.status_code == 400


async def test_follow_missing_target_404(client, make_user):
    _, headers = await make_user("m@example.com", username="muser")
    r = await client.post("/follow", json={"followee_id": 999999}, headers=headers)
    assert r.status_code == 404


async def test_follow_idempotent(client, make_user):
    target, _ = await make_user("t2@example.com", username="ttwo")
    _, headers = await make_user("a2@example.com", username="actortwo")
    for _ in range(2):
        r = await client.post(
            "/follow", json={"followee_id": target["id"]}, headers=headers
        )
        assert r.status_code == 200
    r = await client.get("/users/by-username/ttwo", headers=headers)
    assert r.json()["followers_count"] == 1


async def test_follow_requires_auth(client):
    r = await client.post("/follow", json={"followee_id": 1})
    assert r.status_code in (401, 403)
