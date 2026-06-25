from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import auth, follows, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(follows.router)


@app.get("/healthz")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "postgres": "up" if db_ok else "down",
    }