"""Pydantic-схемы API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------
# Справочники
# --------------------------------------------------------------------------
class LanguageOut(BaseModel):
    code: str
    name: str
    native_name: str | None = None
    flag: str | None = None
    is_source: bool = False


class LangPairOut(BaseModel):
    id: int
    code: str
    source_lang: str
    target_lang: str
    native_label: str | None = None
    enabled: bool = True


class BadgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str | None = None
    emoji: str = "🏅"
    criterion: str
    xp_reward: int = 0
    rarity: str = "common"


# --------------------------------------------------------------------------
# Пользователи
# --------------------------------------------------------------------------
class UserCreate(BaseModel):
    external_id: str | None = None
    name: str | None = None
    username: str | None = None
    role: Literal["student", "teacher"] = "student"
    lang_pair_code: str | None = None
    school_name: str | None = None
    class_name: str | None = None
    avatar: str = "🐝"


class UserOut(BaseModel):
    id: int
    external_id: str | None = None
    name: str | None = None
    username: str | None = None
    role: str = "student"
    avatar: str = "🐝"
    lang_pair_id: int | None = None
    lang_pair_code: str | None = None
    school_id: int | None = None
    class_id: int | None = None
    xp: int = 0
    level: int = 1
    league: str = "bronze"
    streak: int = 0
    longest_streak: int = 0
    gems: int = 0
    hearts: int = 5
    hearts_updated_at: datetime | None = None
    daily_goal: int = 20
    xp_in_level: int = 0
    xp_needed: int = 100
    created_at: datetime


class UserProfileOut(UserOut):
    badges: list[BadgeOut] = []
    stats: dict[str, Any] = {}
    daily_tasks: list["DailyTaskOut"] = []


class LangPairChange(BaseModel):
    lang_pair_code: str


class ClassCreate(BaseModel):
    name: str
    school_name: str | None = None
    teacher_id: int | None = None


class ClassOut(BaseModel):
    id: int
    name: str
    school_id: int | None = None
    school_name: str | None = None
    invite_code: str | None = None
    student_count: int = 0


class JoinClass(BaseModel):
    invite_code: str


# --------------------------------------------------------------------------
# Обучение
# --------------------------------------------------------------------------
class CardOut(BaseModel):
    fragment_id: int
    external_id: str
    text_ba: str
    source: str | None = None
    difficulty: int = 1
    lang_pair: str
    lang_pair_id: int
    translation: str
    is_trap: bool = False          # в вариант намеренно подмешана ошибка
    options: list[str] = []       # варианты ответа (правильный среди них)
    audio_url: str | None = None  # озвучка башкирского фрагмента
    mastery: int = 0


class AnswerIn(BaseModel):
    user_id: int
    fragment_id: int
    lang_pair_id: int
    answer: str = Field(min_length=1, max_length=2000)
    time_spent: float = 0.0
    mode: Literal["normal", "speed", "duel", "chat"] = "normal"


class AnswerOut(BaseModel):
    correct: bool
    correct_translation: str | None = None
    xp_gained: int = 0
    hearts: int = 0
    hearts_lost: bool = False
    level: int = 1
    xp: int = 0
    streak: int = 0
    streak_bonus: int = 0
    new_badges: list[BadgeOut] = []
    daily_progress: dict[str, Any] = {}
    mastery: int = 0
    hint: str | None = None


class DailyTaskOut(BaseModel):
    id: int
    code: str
    title: str
    progress: int
    target: int
    xp_reward: int
    completed: bool


class DailyOut(BaseModel):
    tasks: list[DailyTaskOut]
    cards_done_today: int
    daily_goal: int
    streak: int
    hearts: int
    xp: int
    level: int


# --------------------------------------------------------------------------
# Скоростной режим
# --------------------------------------------------------------------------
class SpeedRunIn(BaseModel):
    user_id: int
    lang_pair_id: int
    score: int = 0
    correct: int = 0
    total: int = 0
    duration: float = 60.0
    best_streak: int = 0


class SpeedRunOut(BaseModel):
    id: int
    score: int
    correct: int
    total: int
    best_streak: int
    duration: float
    xp_gained: int = 0
    new_badges: list[BadgeOut] = []
    created_at: datetime


# --------------------------------------------------------------------------
# Дуэли
# --------------------------------------------------------------------------
class DuelCreate(BaseModel):
    challenger_id: int
    opponent_id: int | None = None
    lang_pair_id: int


class DuelOut(BaseModel):
    id: int
    code: str
    status: str
    lang_pair: str
    fragment_id: int
    text_ba: str
    challenger_id: int
    opponent_id: int | None = None
    challenger_correct: bool | None = None
    opponent_correct: bool | None = None
    winner_id: int | None = None
    created_at: datetime


class DuelAnswerIn(BaseModel):
    duel_id: int
    user_id: int
    answer: str
    time_spent: float = 0.0


class DuelAnswerOut(BaseModel):
    correct: bool
    finished: bool
    winner_id: int | None = None
    comparison: dict[str, Any] = {}


# --------------------------------------------------------------------------
# Рейтинги и статистика
# --------------------------------------------------------------------------
class LeaderboardRow(BaseModel):
    rank: int
    user_id: int
    name: str
    avatar: str = "🐝"
    xp: int = 0
    level: int = 1
    league: str = "bronze"
    streak: int = 0
    accuracy: float = 0.0
    best_speed: int = 0
    wins: int = 0


class GroupRow(BaseModel):
    rank: int
    id: int
    name: str
    school_name: str | None = None
    xp: int = 0
    students: int = 0
    avg_accuracy: float = 0.0


class UserStatsOut(BaseModel):
    user_id: int
    total_answers: int = 0
    correct: int = 0
    accuracy: float = 0.0
    xp: int = 0
    level: int = 1
    league: str = "bronze"
    streak: int = 0
    longest_streak: int = 0
    hearts: int = 5
    gems: int = 0
    vocab_learned: int = 0
    cards_today: int = 0
    daily_goal: int = 20
    speed_runs: int = 0
    best_speed: int = 0
    duels_total: int = 0
    duels_won: int = 0
    accuracy_by_day: list[dict[str, Any]] = []
    activity_by_hour: list[int] = []
    badges: list[BadgeOut] = []


class PlatformStatsOut(BaseModel):
    users: int = 0
    schools: int = 0
    classes: int = 0
    fragments: int = 0
    translations: int = 0
    confirmed_translations: int = 0
    expert_review: int = 0
    answers: int = 0
    speed_runs: int = 0
    duels: int = 0
    active_today: int = 0


# --------------------------------------------------------------------------
# Чат
# --------------------------------------------------------------------------
class ChatIn(BaseModel):
    user_id: int | None = None
    message: str = Field(min_length=1, max_length=2000)
    target_lang: str = "ru"
    history: list[dict[str, str]] = []
    voice_input: bool = False


class ChatOut(BaseModel):
    text_ba: str
    translation: str
    audio: dict[str, Any] | None = None
    clarify: bool = False
    proper: str | None = None
    xp_gained: int = 0
    level: int = 1
    streak: int = 0
    new_badges: list[BadgeOut] = []


class TtsOut(BaseModel):
    url: str
    filename: str
    duration: float
    sample_rate: int


class AsrOut(BaseModel):
    text: str


class ImportStatus(BaseModel):
    running: bool = False
    total_rows: int = 0
    created_fragments: int = 0
    created_translations: int = 0
    finished: bool = False
    error: str | None = None


UserProfileOut.model_rebuild()
