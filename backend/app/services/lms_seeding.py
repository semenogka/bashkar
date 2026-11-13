"""Сидинг демо-данных для фронтенда: пользователи, школы, классы, источники, фрагменты, переводы."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Badge,
    ClassGroup,
    ExpertReview,
    Fragment,
    LangPair,
    PointsEvent,
    School,
    Source,
    TaskAssignment,
    TranslationRecord,
    User,
    UserBadge,
)

logger = logging.getLogger("bashkar.seeding")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEMO_PASSWORD = "password123"

DEMO_USERS = [
    ("student_1", "student", "Student One", 120, 2),
    ("teacher_0_0", "teacher", "Teacher Zero", 0, 1),
    ("expert1", "expert", "Expert One", 40, 1),
    ("admin", "admin", "Admin", 0, 1),
]

DEMO_SCHOOLS = [
    ("Школа №1 г. Уфа", ["10 «А»", "10 «Б»"]),
    ("Гимназия №7 г. Стерлитамак", ["9 «В»"]),
]

FRAGMENTS = [
    ("Башҡортостан — минең тыуған илем.", "Башкортостан — моя родная страна.", "Башҡорт халыҡ әкиәттәре"),
    ("Китап уҡыу — иң яҡшы ял.", "Чтение книг — лучший отдых.", "Башҡорт халыҡ әкиәттәре"),
    ("Әсәй — иң яҡын кеше.", "Мама — самый близкий человек.", "Ғаилә тураһында хикәйәләр"),
    ("Тыуған тел — халыҡтың йәне.", "Родной язык — душа народа.", "Публицистика"),
    ("Балалар — илдең киләсәге.", "Дети — будущее страны.", "Учебный текст"),
    ("Уҡытыусы — белем биреүсе.", "Учитель — дающий знания.", "Учебный текст"),
    ("Дуҫлыҡ — ҙур байлыҡ.", "Дружба — большое богатство.", "Башҡорт халыҡ әкиәттәре"),
    ("Эш — уңыштың нигеҙе.", "Труд — основа успеха.", "Публицистика"),
    ("Тәбиғәтте һаҡлау — һәр кемдең бурысы.", "Охрана природы — долг каждого.", "Экология"),
    ("Сәләмәтлек — иң ҙур байлыҡ.", "Здоровье — самое большое богатство.", "Башҡорт халыҡ әкиәттәре"),
]


async def _get_or_create_source(session: AsyncSession, title: str, source_type: str = "phrasebook") -> Source:
    source = (await session.execute(select(Source).where(Source.title == title))).scalar_one_or_none()
    if source is None:
        source = Source(title=title, source_type=source_type, author="БГПУ им. М. Акмуллы")
        session.add(source)
        await session.flush()
    return source


async def _get_or_create_user(
    session: AsyncSession, username: str, role: str, name: str, points: int, level: int
) -> User:
    user = (await session.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is None:
        user = User(
            username=username,
            email=f"{username}@bashkar.local",
            password_hash=pwd_context.hash(DEMO_PASSWORD),
            role=role,
            name=name,
            xp=points,
            level=level,
            streak=0,
            longest_streak=0,
            hearts=5,
            created_at=datetime.utcnow(),
        )
        session.add(user)
        await session.flush()
    return user


async def seed_all(session: AsyncSession) -> dict:
    """Создаёт демо-данные (идемпотентно). Вызывается из /api/admin/reseed."""
    from app.services.content_import import seed_reference_data

    await seed_reference_data(session)

    stats = {"users": 0, "sources": 0, "fragments": 0, "translations": 0, "reviews": 0, "badges": 0}

    # --- Пользователи ---
    users = {}
    for username, role, name, points, level in DEMO_USERS:
        users[username] = await _get_or_create_user(session, username, role, name, points, level)
        stats["users"] += 1

    # --- Школы и классы ---
    school1 = (await session.execute(select(School).where(School.name == DEMO_SCHOOLS[0][0]))).scalar_one_or_none()
    if school1 is None:
        school1 = School(name=DEMO_SCHOOLS[0][0], city="Уфа")
        session.add(school1)
        await session.flush()
    class_a = (
        await session.execute(
            select(ClassGroup).where(ClassGroup.name == "10 «А»", ClassGroup.school_id == school1.id)
        )
    ).scalar_one_or_none()
    if class_a is None:
        class_a = ClassGroup(name="10 «А»", school_id=school1.id, teacher_id=users["teacher_0_0"].id)
        session.add(class_a)
        await session.flush()

    student = users["student_1"]
    student.school_id = school1.id
    student.class_id = class_a.id

    # --- Источники и фрагменты ---
    pair = (await session.execute(select(LangPair).where(LangPair.code == "ba-ru"))).scalar_one_or_none()
    pair_id = pair.id if pair else None

    for i, (text_ba, auto_translation, source_title) in enumerate(FRAGMENTS):
        source = await _get_or_create_source(session, source_title)
        stats["sources"] += 1

        frag = (
            await session.execute(
                select(Fragment).where(Fragment.text_ba == text_ba, Fragment.lang_pair == "ba-ru")
            )
        ).scalar_one_or_none()
        if frag is None:
            frag = Fragment(
                fragment_id=f"demo-{i + 1}",
                text_ba=text_ba,
                source=source.title,
                source_type=source.source_type,
                topic="phrases",
                difficulty=1,
                source_id=source.id,
                lang_pair="ba-ru",
                auto_translation=auto_translation,
                order_index=i,
            )
            session.add(frag)
            await session.flush()
            stats["fragments"] += 1

        tr = (
            await session.execute(
                select(TranslationRecord).where(TranslationRecord.fragment_id == frag.id)
            )
        ).scalar_one_or_none()
        if tr is None:
            coords = json.dumps(
                {
                    "source_id": source.id,
                    "title": source.title,
                    "author": source.author,
                    "chapter": None,
                    "time_start": None,
                    "time_end": None,
                    "type": source.source_type,
                },
                ensure_ascii=False,
            )
            session.add(
                TranslationRecord(
                    fragment_id=frag.id,
                    text_ba=text_ba,
                    lang_pair="ba-ru",
                    translation=auto_translation,
                    source_coords=coords,
                    confirmed_count=1,
                    status="confirmed",
                )
            )
            stats["translations"] += 1

    await session.flush()

    # --- Экспертная проверка (один спорный случай) ---
    pending = (
        await session.execute(select(ExpertReview).where(ExpertReview.status == "pending"))
    ).scalars().all()
    if not pending and FRAGMENTS:
        first_frag = (
            await session.execute(
                select(Fragment).where(Fragment.lang_pair == "ba-ru").order_by(Fragment.id)
            )
        ).scalars().first()
        if first_frag is not None:
            session.add(
                ExpertReview(
                    fragment_id=first_frag.id,
                    lang_pair="ba-ru",
                    candidates=json.dumps(
                        [["Башкортостан — моя родная страна", 3], ["Башкортостан — мой край", 2]],
                        ensure_ascii=False,
                    ),
                    status="pending",
                )
            )
            stats["reviews"] += 1

    # --- Бейджи и события очков для демо-ученика ---
    student_badges = (
        await session.execute(select(UserBadge.badge_code).where(UserBadge.user_id == student.id))
    ).scalars().all()
    if not student_badges:
        badge = await session.get(Badge, "first_word")
        if badge is not None:
            session.add(UserBadge(user_id=student.id, badge_code=badge.code, earned_at=datetime.utcnow()))
            stats["badges"] += 1
    if student.xp and student.xp > 0:
        session.add(
            PointsEvent(user_id=student.id, points=student.xp, reason="demo_seed", created_at=datetime.utcnow())
        )

    # --- Задание на сегодня для демо-ученика ---
    today = date.today()
    existing = (
        await session.execute(
            select(TaskAssignment).where(
                TaskAssignment.user_id == student.id,
                TaskAssignment.assigned_date == today,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        demo_frag = (
            await session.execute(
                select(Fragment).where(Fragment.lang_pair == "ba-ru").order_by(Fragment.id)
            )
        ).scalars().first()
        if demo_frag is not None:
            session.add(
                TaskAssignment(
                    user_id=student.id,
                    fragment_id=demo_frag.id,
                    variant_translation=demo_frag.auto_translation or "",
                    is_corrupted=False,
                    assigned_date=today,
                )
            )

    await session.commit()
    logger.info("Сидинг завершён: %s", stats)
    return stats
