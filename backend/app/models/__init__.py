"""Все модели платформы."""
from app.models.activity import (
    Badge,
    DailyTask,
    Duel,
    SpeedRun,
    StreakLog,
    UserAnswer,
    UserBadge,
    VocabProgress,
)
from app.models.content import Fragment, LangPair, Language, Translation
from app.models.users import ClassGroup, School, User

__all__ = [
    "Badge",
    "ClassGroup",
    "DailyTask",
    "Duel",
    "Fragment",
    "LangPair",
    "Language",
    "School",
    "SpeedRun",
    "StreakLog",
    "Translation",
    "User",
    "UserAnswer",
    "UserBadge",
    "VocabProgress",
]
