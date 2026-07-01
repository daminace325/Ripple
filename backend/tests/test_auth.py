async def test_register_returns_created(client):
    r = await client.post(
        "/auth/register", json={"email": "a@example.com", "password": "password123"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "a@example.com"
    assert body["username"] is None


async def test_register_duplicate_email_conflict(client):
    payload = {"email": "dup@example.com", "password": "password123"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    r = await client.post("/auth/register", json=payload)
    assert r.status_code == 409


async def test_register_short_password_422(client):
    r = await client.post(
        "/auth/register", json={"email": "x@example.com", "password": "short"}
    )
    assert r.status_code == 422


async def test_login_success(client, make_user):
    await make_user("login@example.com")
    r = await client.post(
        "/auth/login", json={"email": "login@example.com", "password": "password123"}
    )
    assert r.status_code == 200
    assert r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"


async def test_login_wrong_password(client, make_user):
    await make_user("wp@example.com")
    r = await client.post(
        "/auth/login", json={"email": "wp@example.com", "password": "wrongpass"}
    )
    assert r.status_code == 401


async def test_me_requires_auth(client):
    r = await client.get("/users/me")
    assert r.status_code in (401, 403)


async def test_me_invalid_token_401(client):
    r = await client.get("/users/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


async def test_me_returns_user(client, make_user):
    _, headers = await make_user("me@example.com", username="meuser")
    r = await client.get("/users/me", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "meuser"
    assert body["email"] == "me@example.com"
