from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.config import settings
from backend.db.connection import engine
from backend.api import dashboard, query, forecast


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify DB connectivity and validate Anthropic key on startup
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM orders"))
        count = result.scalar()
        print(f"[startup] orders table: {count} rows")

    if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY.startswith("sk-ant-..."):
        print("[startup] WARNING: ANTHROPIC_API_KEY is not configured — AI query endpoint will fail")
    else:
        print("[startup] Anthropic API key configured")

    yield
    await engine.dispose()


app = FastAPI(title="Logistics Analytics Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(dashboard.router, prefix="/api")
app.include_router(query.router,     prefix="/api")
app.include_router(forecast.router,  prefix="/api")
