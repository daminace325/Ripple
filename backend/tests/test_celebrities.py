from app.config import settings
from app.services import celebrities


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
