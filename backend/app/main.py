import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.chat import router as chat_router
from app.api.asr import router as asr_router
app.include_router(chat_router)
app.include_router(asr_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}