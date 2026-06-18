from fastapi import FastAPI

app = FastAPI(title="Ripple Feed")


@app.get("/healthz")
async def health():
    return {"status": "ok"}