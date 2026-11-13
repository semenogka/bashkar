"""Все модели платформы."""
from app.models.activity import (
    Badge,
    DailyChallenge,
    DailyTask,
    Duel,
    SpeedRun,
    StreakLog,
    UserAnswer,
    UserBadge,
    VocabProgress,
)
from app.models.content import Fragment, LangPair, Language, Translation
from app.models.lms import (
    Answer,
    ExpertReview,
    PointsEvent,
    Source,
    TaskAssignment,
    TranslationRecord,
)
from app.models.users import ClassGroup, School, User

__all__ = [
    "Answer",
    "Badge",
    "ClassGroup",
    "DailyChallenge",
    "DailyTask",
    "Duel",
    "ExpertReview",
    "Fragment",
    "LangPair",
    "Language",
    "PointsEvent",
    "School",
    "Source",
    "SpeedRun",
    "StreakLog",
    "TaskAssignment",
    "Translation",
    "TranslationRecord",
    "User",
    "UserAnswer",
    "UserBadge",
    "VocabProgress",
]
