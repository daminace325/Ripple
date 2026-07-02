"""Fan-out worker (separate process).

Consumes ``feed_stream`` via a Redis Streams consumer group and pushes each new post into its
followers' timelines. Run standalone from ``backend/`` (venv active):

    python -m worker.main

At-least-once delivery: a message stays pending until ``XACK``. Crash recovery / reclaim of
dead-consumer messages (``XAUTOCLAIM``), retries, and dead-lettering arrive in Phase 5.
"""

import asyncio
import logging
import os
import socket

from redis.exceptions import ResponseError

from app.config import settings
from app.db import SessionLocal
from app.redis_client import redis_client
from app.services import fanout

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("fanout-worker")

CONSUMER_NAME = f"{socket.gethostname()}-{os.getpid()}"


async def ensure_group() -> None:
    """Create the consumer group (and stream) if it doesn't exist yet."""
    try:
        await redis_client.xgroup_create(
            fanout.FEED_STREAM, fanout.FEED_GROUP, id="0", mkstream=True
        )
        logger.info(
            "created consumer group '%s' on '%s'",
            fanout.FEED_GROUP,
            fanout.FEED_STREAM,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _process(msg_id: str, fields: dict[str, str]) -> None:
    try:
        post_id = int(fields["post_id"])
        author_id = int(fields["author_id"])
        async with SessionLocal() as session:
            await fanout.fan_out_post(session, redis_client, post_id, author_id)
        await redis_client.xack(fanout.FEED_STREAM, fanout.FEED_GROUP, msg_id)
    except Exception:
        # Left unacked on purpose; Phase 5 adds reclaim + dead-letter.
        logger.exception("fan-out failed for message %s", msg_id)


async def run() -> None:
    await ensure_group()
    logger.info("fan-out worker started as %s", CONSUMER_NAME)
    while True:
        resp = await redis_client.xreadgroup(
            fanout.FEED_GROUP,
            CONSUMER_NAME,
            {fanout.FEED_STREAM: ">"},
            count=settings.worker_batch_size,
            block=settings.worker_block_ms,
        )
        if not resp:
            continue
        for _stream, messages in resp:
            # Process the batch concurrently — each message overlaps its DB/Redis I/O.
            await asyncio.gather(
                *(_process(msg_id, fields) for msg_id, fields in messages)
            )


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("fan-out worker stopped")
