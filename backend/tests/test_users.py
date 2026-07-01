async def test_patch_me_sets_username(client, make_user):
    _, headers = await make_user("u1@example.com")
    r = await client.patch(
        "/users/me",
        json={"username": "alice", "display_name": "Alice"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["username"] == "alice"
    assert r.json()["display_name"] == "Alice"


async def test_patch_me_duplicate_username_conflict(client, make_user):
    await make_user("taken@example.com", username="taken")
    _, headers = await make_user("other@example.com")
    r = await client.patch("/users/me", json={"username": "taken"}, headers=headers)
    assert r.status_code == 409


async def test_patch_me_short_username_422(client, make_user):
    _, headers = await make_user("sh@example.com")
    r = await client.patch("/users/me", json={"username": "ab"}, headers=headers)
    assert r.status_code == 422


async def test_get_user_by_id(client, make_user):
    target, _ = await make_user("target@example.com", username="target")
    _, headers = await make_user("viewer@example.com", username="viewer")
    r = await client.get(f"/users/{target['id']}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "target"
    assert "email" not in body


async def test_get_user_by_id_missing_404(client, make_user):
    _, headers = await make_user("v2@example.com", username="vtwo")
    r = await client.get("/users/999999", headers=headers)
    assert r.status_code == 404


async def test_search_excludes_self_and_finds(client, make_user):
    _, headers = await make_user("searcher@example.com", username="searcher")
    await make_user("findme@example.com", username="findme")
    r = await client.get("/users/search", params={"q": "find"}, headers=headers)
    assert r.status_code == 200
    names = [u["username"] for u in r.json()]
    assert "findme" in names
    assert "searcher" not in names


async def test_profile_by_username_counts_and_following(client, make_user):
    target, _ = await make_user("prof@example.com", username="prof")
    _, fheaders = await make_user("fol@example.com", username="fol")
    await client.post("/follow", json={"followee_id": target["id"]}, headers=fheaders)
    r = await client.get("/users/by-username/prof", headers=fheaders)
    assert r.status_code == 200
    body = r.json()
    assert body["followers_count"] == 1
    assert body["is_following"] is True


async def test_profile_by_username_missing_404(client, make_user):
    _, headers = await make_user("nobody@example.com", username="nobody")
    r = await client.get("/users/by-username/ghost", headers=headers)
    assert r.status_code == 404
