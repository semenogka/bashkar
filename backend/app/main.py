"""Точка входа FastAPI: Башкирская языковая школа."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from app.core.config import settings
from app.db.base import SessionFactory, engine, init_models
from app.models import Fragment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bashkar")

from app.api.chat import router as chat_router  # noqa: E402
from app.api.content import router as content_router  # noqa: E402
from app.api.duels import router as duels_router  # noqa: E402
from app.api.learn import router as learn_router  # noqa: E402
from app.api.leaderboard import router as leaderboard_router  # noqa: E402
from app.api.speech import router as speech_router  # noqa: E402
from app.api.speed import router as speed_router  # noqa: E402
from app.api.stats import router as stats_router  # noqa: E402
from app.api.users import router as users_router  # noqa: E402
from app.services.content_import import import_phrasebooks, seed_reference_data  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Инициализация БД: %s", settings.database_url.split("@")[-1])
    await init_models()
    async with SessionFactory() as session:
        await seed_reference_data(session)
        count = (await session.execute(select(func.count()).select_from(Fragment))).scalar_one()
        has_content = count > 0
    if not has_content and Path(settings.dataset_file).exists():
        logger.info("Импортирую датасет %s", settings.dataset_file)
        async with SessionFactory() as session:
            result = await import_phrasebooks(session)
        logger.info("Импорт завершён: %s", result)
    logger.info("Готов к работе 🐝")
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description=(
        "API платформы «Башкирская языковая школа»: обучение, геймификация, "
        "дуэли, быстрый перевод, рейтинги, чат-репетитор с озвучкой и распознаванием речи."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    users_router,
    learn_router,
    speed_router,
    duels_router,
    leaderboard_router,
    stats_router,
    chat_router,
    speech_router,
    content_router,
):
    app.include_router(router, prefix=settings.api_prefix)

app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


@app.get("/health", tags=["system"])
async def health():
    async with SessionFactory() as session:
        from sqlalchemy import func, select

        from app.models import Fragment, User

        users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        fragments = (await session.execute(select(func.count()).select_from(Fragment))).scalar_one()
    return {
        "status": "ok",
        "app": settings.app_name,
        "users": users,
        "fragments": fragments,
        "db": "postgresql",
    }
