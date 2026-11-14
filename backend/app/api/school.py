"""Школы, учителя, классы, домашние задания и словарь по базе фраз."""
from __future__ import annotations

import csv
import io
import random
import string
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import _create_jwt, get_current_user_v1
from app.db.base import get_session
from app.models import (
    ClassAssignment,
    ClassAssignmentAnswer,
    ClassAssignmentItem,
    ClassGroup,
    Fragment,
    LangPair,
    PointsEvent,
    School,
    Translation,
    User,
)
from app.services.agreement import normalize, similarity
from app.services.gamification import add_xp, touch_streak
from app.services.passwords import hash_password

router = APIRouter(tags=["school"])

HOMEWORK_XP = 12


class SchoolIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    city: str | None = Field(default=None, max_length=80)


class AccountIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=4, max_length=72)
    name: str | None = Field(default=None, max_length=128)
    role: str = "student"
    school_code: str | None = None
    class_code: str | None = None


class CodeIn(BaseModel):
    invite_code: str = Field(min_length=4, max_length=16)


class BecomeTeacherIn(BaseModel):
    school_code: str = Field(min_length=4, max_length=16)
    name: str | None = Field(default=None, max_length=128)


class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AssignmentIn(BaseModel):
    class_id: int
    title: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    fragment_ids: list[int] = []
    auto_count: int = 0


class HomeworkAnswerIn(BaseModel):
    item_id: int
    answer: str = Field(min_length=1, max_length=2000)


def _is_guest(user: User) -> bool:
    return user.username == "guest" and not user.external_id and not user.password_hash


def _clean_code(value: str | None) -> str:
    return (value or "").strip().upper()


async def _unique_code(session: AsyncSession, model, column) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(10):
        code = "".join(random.choices(alphabet, k=6))
        found = (
            await session.execute(select(model.id).where(column == code))
        ).scalar_one_or_none()
        if found is None:
            return code
    raise HTTPException(500, "Не удалось выдать код приглашения")


async def _ensure_school_code(session: AsyncSession, school: School) -> None:
    if school.invite_code:
        return
    school.invite_code = await _unique_code(session, School, School.invite_code)


async def _school_by_code(session: AsyncSession, code: str) -> School:
    school = (
        await session.execute(select(School).where(func.upper(School.invite_code) == _clean_code(code)))
    ).scalar_one_or_none()
    if school is None:
        raise HTTPException(404, "Школа с таким кодом не найдена")
    return school


async def _class_by_code(session: AsyncSession, code: str) -> ClassGroup:
    klass = (
        await session.execute(
            select(ClassGroup).where(func.upper(ClassGroup.invite_code) == _clean_code(code))
        )
    ).scalar_one_or_none()
    if klass is None:
        raise HTTPException(404, "Класс с таким кодом не найден")
    return klass


def _require_real_user(user: User) -> None:
    if _is_guest(user):
        raise HTTPException(403, "Сначала зарегистрируйтесь: гостевой профиль общий для всех")


async def _school_brief(session: AsyncSession, school: School | None, *, with_code: bool) -> dict | None:
    if school is None:
        return None
    await _ensure_school_code(session, school)
    students = (
        await session.execute(
            select(func.count()).select_from(User).where(User.school_id == school.id, User.role == "student")
        )
    ).scalar_one()
    data = {
        "id": school.id,
        "name": school.name,
        "city": school.city,
        "students": int(students or 0),
    }
    if with_code:
        data["invite_code"] = school.invite_code
    return data


async def _class_brief(session: AsyncSession, klass: ClassGroup | None) -> dict | None:
    if klass is None:
        return None
    students = (
        await session.execute(
            select(func.count()).select_from(User).where(User.class_id == klass.id, User.role == "student")
        )
    ).scalar_one()
    school_name = None
    if klass.school_id:
        school = await session.get(School, klass.school_id)
        school_name = school.name if school else None
    teacher_name = None
    if klass.teacher_id:
        teacher = await session.get(User, klass.teacher_id)
        teacher_name = (teacher.name or teacher.username) if teacher else None
    return {
        "id": klass.id,
        "name": klass.name,
        "school_id": klass.school_id,
        "school_name": school_name,
        "teacher_name": teacher_name,
        "invite_code": klass.invite_code,
        "students": int(students or 0),
    }


async def _expected_translation(session: AsyncSession, fragment: Fragment) -> str:
    if fragment.auto_translation and fragment.auto_translation.strip():
        return fragment.auto_translation.strip()
    text = (
        await session.execute(
            select(Translation.translation)
            .join(LangPair, LangPair.id == Translation.lang_pair_id)
            .where(Translation.fragment_id == fragment.id)
            .order_by(case((LangPair.code == "ba-ru", 0), else_=1), Translation.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return (text or "").strip()


def _is_match(answer: str, expected: str) -> bool:
    if not expected:
        return False
    if normalize(answer) == normalize(expected):
        return True
    return similarity(answer, expected) >= 0.8


async def _pick_fragments(session: AsyncSession, ids: list[int], auto_count: int) -> list[Fragment]:
    chosen: list[Fragment] = []
    if ids:
        rows = (
            await session.execute(select(Fragment).where(Fragment.id.in_(ids[:40])))
        ).scalars().all()
        by_id = {row.id: row for row in rows}
        seen_ids: set[int] = set()
        for frag_id in ids:
            frag = by_id.get(frag_id)
            if frag is not None and frag.id not in seen_ids:
                seen_ids.add(frag.id)
                chosen.append(frag)
    elif auto_count:
        n = max(1, min(30, auto_count))
        chosen = (
            await session.execute(
                select(Fragment)
                .where(Fragment.auto_translation.isnot(None), Fragment.auto_translation != "")
                .order_by(func.random())
                .limit(n)
            )
        ).scalars().all()
        if len(chosen) < n:
            extra = (
                await session.execute(
                    select(Fragment)
                    .join(Translation, Translation.fragment_id == Fragment.id)
                    .order_by(func.random())
                    .limit(n)
                )
            ).scalars().all()
            seen = {f.id for f in chosen}
            for frag in extra:
                if frag.id not in seen:
                    chosen.append(frag)
                    seen.add(frag.id)
                if len(chosen) >= n:
                    break
    else:
        raise HTTPException(400, "Выберите фразы из словаря или укажите, сколько выдать автоматически")

    usable: list[Fragment] = []
    for frag in chosen:
        if await _expected_translation(session, frag):
            usable.append(frag)
    if not usable:
        raise HTTPException(400, "В базе нет фраз с переводом для такого задания")
    return usable[:40]


async def _assignment_progress(session: AsyncSession, assignment: ClassAssignment, user: User) -> dict:
    items = (
        await session.execute(
            select(ClassAssignmentItem).where(ClassAssignmentItem.assignment_id == assignment.id)
        )
    ).scalars().all()
    item_ids = [item.id for item in items]
    answered = correct = 0
    if item_ids:
        answered = (
            await session.execute(
                select(func.count()).select_from(ClassAssignmentAnswer).where(
                    ClassAssignmentAnswer.user_id == user.id,
                    ClassAssignmentAnswer.item_id.in_(item_ids),
                )
            )
        ).scalar_one()
        correct = (
            await session.execute(
                select(func.count()).select_from(ClassAssignmentAnswer).where(
                    ClassAssignmentAnswer.user_id == user.id,
                    ClassAssignmentAnswer.item_id.in_(item_ids),
                    ClassAssignmentAnswer.is_correct.is_(True),
                )
            )
        ).scalar_one()
    students = (
        await session.execute(
            select(func.count()).select_from(User).where(
                User.class_id == assignment.class_id, User.role == "student"
            )
        )
    ).scalar_one()
    finished = 0
    if item_ids and students:
        per_user = (
            await session.execute(
                select(ClassAssignmentAnswer.user_id, func.count())
                .where(ClassAssignmentAnswer.item_id.in_(item_ids))
                .group_by(ClassAssignmentAnswer.user_id)
            )
        ).all()
        total = len(item_ids)
        finished = sum(1 for _uid, count in per_user if int(count) >= total)
    klass = await session.get(ClassGroup, assignment.class_id)
    return {
        "id": assignment.id,
        "class_id": assignment.class_id,
        "class_name": klass.name if klass else None,
        "title": assignment.title,
        "note": assignment.note,
        "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
        "created_at": assignment.created_at,
        "items_total": len(item_ids),
        "answered": int(answered or 0),
        "correct": int(correct or 0),
        "students": int(students or 0),
        "finished": int(finished),
        "can_answer": user.class_id == assignment.class_id and user.id != assignment.teacher_id,
        "can_manage": user.id == assignment.teacher_id,
    }


@router.get("/v1/dictionary")
async def dictionary(
    q: str = "",
    lang: str = "ru",
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Поиск перевода слова или фразы по базе."""
    query = (q or "").strip()
    wanted = "ba-" + (lang if lang in {"ru", "kk", "zh"} else "ru")

    def _stmt(codes: list[str]):
        stmt = (
            select(Fragment, Translation, LangPair)
            .join(Translation, Translation.fragment_id == Fragment.id)
            .join(LangPair, LangPair.id == Translation.lang_pair_id)
            .where(LangPair.code.in_(codes))
        )
        if query:
            pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            exact = case((func.lower(Fragment.text_ba) == query.lower(), 0), else_=1)
            stmt = stmt.where(
                or_(
                    Fragment.text_ba.ilike(pattern, escape="\\"),
                    Translation.translation.ilike(pattern, escape="\\"),
                )
            ).order_by(exact, func.length(Fragment.text_ba), Fragment.id)
        else:
            stmt = stmt.order_by(Fragment.difficulty, func.length(Fragment.text_ba), Fragment.id)
        return stmt

    rows = (await session.execute(_stmt([wanted]).limit(limit * 4))).all()
    if query and wanted != "ba-ru" and not rows:
        have = {frag.id for frag, _, _ in rows}
        if len(have) < limit:
            extra = (await session.execute(_stmt(["ba-ru"]).limit(limit * 4))).all()
            for item in extra:
                if item[0].id in have:
                    continue
                rows.append(item)
                have.add(item[0].id)
    best: dict[int, dict] = {}
    order: list[int] = []
    for frag, trans, _pair in rows:
        text = (trans.translation or "").strip()
        if not text or frag.id in best:
            continue
        best[frag.id] = {
            "fragment_id": frag.id,
            "bashkir": frag.text_ba,
            "translation": text,
            "topic": frag.topic,
            "difficulty": frag.difficulty or 1,
            "source": frag.source,
        }
        order.append(frag.id)
        if len(order) >= limit:
            break
    return {"query": query, "lang": wanted.split("-", 1)[1], "items": [best[i] for i in order]}


@router.get("/v1/school/rankings/schools")
async def rank_schools(limit: int = Query(default=50, ge=1, le=100), session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(
                School.id,
                School.name,
                School.city,
                func.count(User.id),
                func.coalesce(func.sum(User.xp), 0),
            )
            .join(User, (User.school_id == School.id) & (User.role == "student"), isouter=True)
            .group_by(School.id, School.name, School.city)
            .order_by(func.coalesce(func.sum(User.xp), 0).desc(), School.name)
            .limit(limit)
        )
    ).all()
    result = []
    for rank, (sid, name, city, students, xp) in enumerate(rows, start=1):
        students_n = int(students or 0)
        xp_n = int(xp or 0)
        result.append({
            "rank": rank,
            "id": sid,
            "name": name,
            "city": city,
            "school_name": name,
            "students": students_n,
            "xp": xp_n,
            "avg_xp": int(xp_n / students_n) if students_n else 0,
        })
    return result


@router.get("/v1/school/rankings/classes")
async def rank_classes(
    school_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    stmt = (
        select(
            ClassGroup.id,
            ClassGroup.name,
            ClassGroup.school_id,
            School.name,
            func.count(User.id),
            func.coalesce(func.sum(User.xp), 0),
        )
        .join(User, User.class_id == ClassGroup.id, isouter=True)
        .join(School, School.id == ClassGroup.school_id, isouter=True)
        .group_by(ClassGroup.id, ClassGroup.name, ClassGroup.school_id, School.name)
        .order_by(func.coalesce(func.sum(User.xp), 0).desc(), ClassGroup.name)
        .limit(limit)
    )
    if school_id is not None:
        stmt = stmt.where(ClassGroup.school_id == school_id).limit(limit)
    rows = (await session.execute(stmt)).all()
    result = []
    for rank, (cid, name, sid, school_name, students, xp) in enumerate(rows, start=1):
        students_n = int(students or 0)
        xp_n = int(xp or 0)
        result.append({
            "rank": rank,
            "id": cid,
            "name": name,
            "school_id": sid,
            "school_name": school_name,
            "students": students_n,
            "xp": xp_n,
            "avg_xp": int(xp_n / students_n) if students_n else 0,
        })
    return result


@router.post("/v1/school/schools")
async def register_school(
    payload: SchoolIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    school = School(
        name=payload.name.strip(),
        city=(payload.city or "").strip() or None,
        invite_code=await _unique_code(session, School, School.invite_code),
        created_at=datetime.utcnow(),
    )
    session.add(school)
    await session.flush()
    token = None
    if not _is_guest(user) and user.school_id is None:
        user.school_id = school.id
        user.role = "teacher"
        token = _create_jwt(user)
    await session.commit()
    await session.refresh(school)
    return {
        "id": school.id,
        "name": school.name,
        "city": school.city,
        "invite_code": school.invite_code,
        "access_token": token,
        "hint": "Передайте этот код учителям. По нему они привяжутся к школе.",
    }


@router.post("/v1/school/register")
async def register_account(
    payload: AccountIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    username = payload.username.strip()
    if username.lower() == "guest" or " " in username:
        raise HTTPException(400, "Имя пользователя не подходит")
    role = payload.role if payload.role in ("teacher", "student") else "student"
    existing = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Такое имя пользователя уже занято")

    school = None
    klass = None
    if role == "teacher":
        if not payload.school_code:
            raise HTTPException(400, "Учителю нужен код школы")
        school = await _school_by_code(session, payload.school_code)
    elif payload.class_code:
        klass = await _class_by_code(session, payload.class_code)
        if klass.school_id:
            school = await session.get(School, klass.school_id)

    pair = (
        await session.execute(select(LangPair).where(LangPair.code == "ba-ru"))
    ).scalar_one_or_none()
    user = User(
        username=username,
        name=(payload.name or username).strip(),
        password_hash=hash_password(payload.password),
        role=role,
        school_id=school.id if school else None,
        class_id=klass.id if klass else None,
        lang_pair_id=pair.id if pair else None,
        avatar="🐝",
        hearts=5,
        created_at=datetime.utcnow(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {
        "access_token": _create_jwt(user),
        "token_type": "bearer",
        "id": user.id,
        "name": user.name,
        "username": user.username,
        "role": user.role,
        "school_id": user.school_id,
        "class_id": user.class_id,
    }


@router.get("/v1/school/me")
async def school_me(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    school = await session.get(School, user.school_id) if user.school_id else None
    klass = await session.get(ClassGroup, user.class_id) if user.class_id else None
    teaching_rows = (
        await session.execute(
            select(ClassGroup).where(ClassGroup.teacher_id == user.id).order_by(ClassGroup.id)
        )
    ).scalars().all()
    teaching = []
    for row in teaching_rows:
        brief = await _class_brief(session, row)
        if brief:
            teaching.append(brief)
    school_payload = await _school_brief(session, school, with_code=user.role == "teacher")
    class_payload = await _class_brief(session, klass)
    await session.commit()
    return {
        "id": user.id,
        "name": user.name or user.username,
        "username": user.username,
        "role": user.role,
        "is_guest": _is_guest(user),
        "xp": user.xp or 0,
        "level": user.level or 1,
        "school": school_payload,
        "class": class_payload,
        "teaching": teaching,
    }


@router.post("/v1/school/become-teacher")
async def become_teacher(
    payload: BecomeTeacherIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_real_user(user)
    school = await _school_by_code(session, payload.school_code)
    user.role = "teacher"
    user.school_id = school.id
    if payload.name:
        user.name = payload.name.strip()
    if user.class_id:
        klass = await session.get(ClassGroup, user.class_id)
        if klass and klass.school_id != school.id:
            user.class_id = None
    await session.commit()
    return {"ok": True, "role": user.role, "school_id": school.id, "access_token": _create_jwt(user)}


@router.post("/v1/school/classes")
async def create_class(
    payload: ClassIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_real_user(user)
    if user.role != "teacher":
        raise HTTPException(403, "Класс создаёт учитель")
    if not user.school_id:
        raise HTTPException(400, "Сначала привяжите школу по коду")
    klass = ClassGroup(
        name=payload.name.strip(),
        school_id=user.school_id,
        teacher_id=user.id,
        invite_code=await _unique_code(session, ClassGroup, ClassGroup.invite_code),
        created_at=datetime.utcnow(),
    )
    session.add(klass)
    await session.commit()
    await session.refresh(klass)
    brief = await _class_brief(session, klass)
    return brief


@router.post("/v1/school/join")
async def join_class(
    payload: CodeIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_real_user(user)
    if user.role == "teacher":
        raise HTTPException(400, "Учитель не вступает в класс учеником. Создайте свой класс.")
    klass = await _class_by_code(session, payload.invite_code)
    user.class_id = klass.id
    user.school_id = klass.school_id
    await session.commit()
    return {"ok": True, "class": await _class_brief(session, klass)}


@router.get("/v1/school/assignments")
async def list_assignments(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> list[dict]:
    conds = []
    if user.role == "teacher":
        conds.append(ClassAssignment.teacher_id == user.id)
    if user.class_id:
        conds.append(ClassAssignment.class_id == user.class_id)
    if not conds:
        return []
    rows = (
        await session.execute(
            select(ClassAssignment).where(or_(*conds)).order_by(ClassAssignment.created_at.desc())
        )
    ).scalars().all()
    return [await _assignment_progress(session, row, user) for row in rows]


@router.post("/v1/school/assignments")
async def create_assignment(
    payload: AssignmentIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_real_user(user)
    if user.role != "teacher":
        raise HTTPException(403, "Задания выдаёт учитель")
    klass = await session.get(ClassGroup, payload.class_id)
    if klass is None or klass.teacher_id != user.id:
        raise HTTPException(403, "Это не ваш класс")
    fragments = await _pick_fragments(session, payload.fragment_ids, payload.auto_count)
    assignment = ClassAssignment(
        class_id=klass.id,
        teacher_id=user.id,
        title=payload.title.strip(),
        note=(payload.note or "").strip() or None,
        due_date=payload.due_date,
        created_at=datetime.utcnow(),
    )
    session.add(assignment)
    await session.flush()
    for index, frag in enumerate(fragments):
        session.add(ClassAssignmentItem(
            assignment_id=assignment.id,
            fragment_id=frag.id,
            order_index=index,
        ))
    await session.commit()
    await session.refresh(assignment)
    data = await _assignment_progress(session, assignment, user)
    data["created_items"] = len(fragments)
    return data


@router.get("/v1/school/assignments/{assignment_id}")
async def assignment_detail(
    assignment_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    assignment = await session.get(ClassAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(404, "Задание не найдено")
    can_manage = user.id == assignment.teacher_id
    can_answer = user.class_id == assignment.class_id and user.id != assignment.teacher_id
    if not can_manage and not can_answer:
        raise HTTPException(403, "Это задание другого класса")
    items = (
        await session.execute(
            select(ClassAssignmentItem)
            .where(ClassAssignmentItem.assignment_id == assignment.id)
            .order_by(ClassAssignmentItem.order_index, ClassAssignmentItem.id)
        )
    ).scalars().all()
    answers = {}
    if items:
        rows = (
            await session.execute(
                select(ClassAssignmentAnswer).where(
                    ClassAssignmentAnswer.user_id == user.id,
                    ClassAssignmentAnswer.item_id.in_([item.id for item in items]),
                )
            )
        ).scalars().all()
        answers = {row.item_id: row for row in rows}
    item_stats: dict[int, tuple[int, int]] = {}
    if can_manage and items:
        grouped = (
            await session.execute(
                select(
                    ClassAssignmentAnswer.item_id,
                    func.count(),
                    func.coalesce(func.sum(case((ClassAssignmentAnswer.is_correct.is_(True), 1), else_=0)), 0),
                )
                .where(ClassAssignmentAnswer.item_id.in_([item.id for item in items]))
                .group_by(ClassAssignmentAnswer.item_id)
            )
        ).all()
        item_stats = {item_id: (int(total), int(ok)) for item_id, total, ok in grouped}
    payload_items = []
    for item in items:
        frag = await session.get(Fragment, item.fragment_id)
        if frag is None:
            continue
        answer = answers.get(item.id)
        show_translation = can_manage or answer is not None
        expected = await _expected_translation(session, frag) if show_translation else None
        entry = {
            "id": item.id,
            "fragment_id": frag.id,
            "bashkir": frag.text_ba,
            "topic": frag.topic,
            "answered": answer is not None,
            "is_correct": bool(answer.is_correct) if answer else False,
            "your_answer": answer.answer if answer else None,
            "translation": expected if show_translation else None,
        }
        if can_manage:
            total, ok = item_stats.get(item.id, (0, 0))
            entry["answer_count"] = total
            entry["correct_count"] = ok
        payload_items.append(entry)
    data = await _assignment_progress(session, assignment, user)
    data["items"] = payload_items
    return data


@router.post("/v1/school/assignments/{assignment_id}/answers")
async def answer_assignment(
    assignment_id: int,
    payload: HomeworkAnswerIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_real_user(user)
    assignment = await session.get(ClassAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(404, "Задание не найдено")
    if user.class_id != assignment.class_id or user.id == assignment.teacher_id:
        raise HTTPException(403, "Отвечать могут ученики этого класса")
    item = await session.get(ClassAssignmentItem, payload.item_id)
    if item is None or item.assignment_id != assignment.id:
        raise HTTPException(404, "Пункт задания не найден")
    existing = (
        await session.execute(
            select(ClassAssignmentAnswer).where(
                ClassAssignmentAnswer.item_id == item.id,
                ClassAssignmentAnswer.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    frag = await session.get(Fragment, item.fragment_id)
    if frag is None:
        raise HTTPException(404, "Фраза не найдена")
    expected = await _expected_translation(session, frag)
    if existing:
        return {
            "correct": existing.is_correct,
            "expected": expected,
            "xp_gained": 0,
            "already": True,
            "xp": user.xp or 0,
            "level": user.level or 1,
        }
    correct = _is_match(payload.answer, expected)
    session.add(ClassAssignmentAnswer(
        item_id=item.id,
        user_id=user.id,
        answer=payload.answer.strip(),
        is_correct=correct,
        created_at=datetime.utcnow(),
    ))
    gained = HOMEWORK_XP if correct else 0
    if gained:
        add_xp(user, gained, session, reason="homework")
        await touch_streak(session, user, xp=gained)
    await session.commit()
    return {
        "correct": correct,
        "expected": expected,
        "xp_gained": gained,
        "already": False,
        "xp": user.xp or 0,
        "level": user.level or 1,
    }


@router.get("/v1/school/classes/{class_id}/stats")
async def class_stats(
    class_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    klass = await session.get(ClassGroup, class_id)
    if klass is None:
        raise HTTPException(404, "Класс не найден")
    if klass.teacher_id != user.id and user.class_id != klass.id:
        raise HTTPException(403, "Статистика доступна классу и его учителю")
    students = (
        await session.execute(
            select(User).where(User.class_id == klass.id, User.role == "student").order_by(User.xp.desc())
        )
    ).scalars().all()
    assignments = (
        await session.execute(
            select(ClassAssignment).where(ClassAssignment.class_id == klass.id)
        )
    ).scalars().all()
    item_rows = []
    if assignments:
        item_rows = (
            await session.execute(
                select(ClassAssignmentItem.id, ClassAssignmentItem.assignment_id).where(
                    ClassAssignmentItem.assignment_id.in_([a.id for a in assignments])
                )
            )
        ).all()
    items_by_assignment: dict[int, list[int]] = {}
    for item_id, assignment_id in item_rows:
        items_by_assignment.setdefault(assignment_id, []).append(item_id)
    answer_rows = []
    all_item_ids = [item_id for ids in items_by_assignment.values() for item_id in ids]
    if all_item_ids:
        answer_rows = (
            await session.execute(
                select(
                    ClassAssignmentAnswer.user_id,
                    ClassAssignmentAnswer.item_id,
                    ClassAssignmentAnswer.is_correct,
                ).where(ClassAssignmentAnswer.item_id.in_(all_item_ids))
            )
        ).all()
    by_user: dict[int, list[tuple[int, bool]]] = {}
    for uid, item_id, ok in answer_rows:
        by_user.setdefault(uid, []).append((item_id, bool(ok)))
    student_payload = []
    for student in students:
        pairs = by_user.get(student.id, [])
        done_assignments = 0
        for ids in items_by_assignment.values():
            if ids and all(any(item_id == i for item_id, _ok in pairs) for i in ids):
                done_assignments += 1
        student_payload.append({
            "id": student.id,
            "name": student.name or student.username or f"Ученик {student.id}",
            "xp": student.xp or 0,
            "level": student.level or 1,
            "streak": student.streak or 0,
            "answered": len(pairs),
            "correct": sum(1 for _item, ok in pairs if ok),
            "assignments_done": done_assignments,
            "assignments_total": len(assignments),
        })
    return {
        "class": await _class_brief(session, klass),
        "assignments_total": len(assignments),
        "students": student_payload,
    }


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(403, "Нужна роль администратора")


def _public_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name or user.username or f"Ученик {user.id}",
        "role": user.role,
        "school_id": user.school_id,
        "class_id": user.class_id,
        "xp": user.xp or 0,
    }


async def _user_by_username(session: AsyncSession, username: str) -> User:
    found = (
        await session.execute(
            select(User).where(func.lower(User.username) == username.strip().lower())
        )
    ).scalar_one_or_none()
    if found is None or _is_guest(found):
        raise HTTPException(404, "Пользователь с таким логином не найден")
    return found


class AdminClassIn(BaseModel):
    school_id: int
    name: str = Field(min_length=1, max_length=120)
    teacher_username: str | None = Field(default=None, max_length=64)


class AdminAssignIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    role: str = "student"
    school_id: int | None = None
    class_id: int | None = None


class AddStudentIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    class_id: int | None = None


@router.get("/v1/dictionary/export")
async def dictionary_export(session: AsyncSession = Depends(get_session)):
    """Весь словарь: башкирская фраза и русский перевод."""
    rows = (
        await session.execute(
            select(Fragment, Translation)
            .outerjoin(Translation, Translation.fragment_id == Fragment.id)
            .order_by(func.length(Fragment.text_ba), Fragment.id)
        )
    ).all()
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["bashkir", "russian", "topic", "difficulty"])
    seen: set[int] = set()
    for frag, trans in rows:
        if frag.id in seen:
            continue
        russian = ""
        if trans is not None and trans.translation:
            russian = trans.translation.strip()
        if not russian and frag.auto_translation:
            russian = frag.auto_translation.strip()
        if not russian or not frag.text_ba:
            continue
        seen.add(frag.id)
        writer.writerow([frag.text_ba, russian, frag.topic or "", frag.difficulty or 1])
    payload = buf.getvalue()
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="beztel-dictionary.csv"'},
    )


@router.get("/v1/admin/board")
async def admin_board(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_admin(user)
    schools = (await session.execute(select(School).order_by(School.name))).scalars().all()
    classes = (await session.execute(select(ClassGroup).order_by(ClassGroup.name))).scalars().all()
    teacher_ids = {row.teacher_id for row in classes if row.teacher_id}
    teachers = {}
    if teacher_ids:
        found = (
            await session.execute(select(User).where(User.id.in_(teacher_ids)))
        ).scalars().all()
        teachers = {row.id: row for row in found}
    return {
        "schools": [
            {"id": school.id, "name": school.name, "city": school.city or ""}
            for school in schools
        ],
        "classes": [
            {
                "id": row.id,
                "name": row.name,
                "school_id": row.school_id,
                "teacher_id": row.teacher_id,
                "teacher_name": (
                    (teachers[row.teacher_id].name or teachers[row.teacher_id].username)
                    if row.teacher_id in teachers else None
                ),
            }
            for row in classes
        ],
    }


@router.get("/v1/admin/users")
async def admin_users(
    q: str = "",
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_admin(user)
    stmt = select(User).where(User.username.isnot(None), User.username != "guest")
    query = (q or "").strip()
    if query:
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(User.username.ilike(pattern, escape="\\"), User.name.ilike(pattern, escape="\\")))
    rows = (await session.execute(stmt.order_by(User.id.desc()).limit(40))).scalars().all()
    return {"users": [_public_user(row) for row in rows]}


@router.post("/v1/admin/schools")
async def admin_create_school(
    payload: SchoolIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_admin(user)
    school = School(name=payload.name.strip(), city=(payload.city or "").strip() or None)
    school.invite_code = await _unique_code(session, School, School.invite_code)
    session.add(school)
    await session.commit()
    await session.refresh(school)
    return {"id": school.id, "name": school.name, "city": school.city or ""}


@router.post("/v1/admin/classes")
async def admin_create_class(
    payload: AdminClassIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    _require_admin(user)
    school = await session.get(School, payload.school_id)
    if school is None:
        raise HTTPException(404, "Школа не найдена")
    teacher = None
    if payload.teacher_username and payload.teacher_username.strip():
        teacher = await _user_by_username(session, payload.teacher_username)
        if teacher.role == "admin":
            raise HTTPException(400, "Администратора нельзя назначить учителем класса")
        teacher.role = "teacher"
        teacher.school_id = school.id
    klass = ClassGroup(
        name=payload.name.strip(),
        school_id=school.id,
        teacher_id=teacher.id if teacher else None,
        invite_code=await _unique_code(session, ClassGroup, ClassGroup.invite_code),
    )
    session.add(klass)
    await session.flush()
    if teacher is not None:
        teacher.class_id = klass.id
    await session.commit()
    await session.refresh(klass)
    return {
        "id": klass.id,
        "name": klass.name,
        "school_id": school.id,
        "teacher_name": (teacher.name or teacher.username) if teacher else None,
    }


@router.post("/v1/admin/assign")
async def admin_assign(
    payload: AdminAssignIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    """Привязать пользователя к школе, классу и роли."""
    _require_admin(user)
    target = await _user_by_username(session, payload.username)
    if target.id == user.id:
        raise HTTPException(400, "Свою роль администратора менять здесь нельзя")
    role = payload.role if payload.role in ("teacher", "student") else "student"
    klass = await session.get(ClassGroup, payload.class_id) if payload.class_id else None
    if payload.class_id and klass is None:
        raise HTTPException(404, "Класс не найден")
    school_id = payload.school_id or (klass.school_id if klass else None)
    if school_id:
        school = await session.get(School, school_id)
        if school is None:
            raise HTTPException(404, "Школа не найдена")
    if klass and school_id and klass.school_id != school_id:
        raise HTTPException(400, "Класс относится к другой школе")
    target.role = role
    target.school_id = school_id
    target.class_id = klass.id if klass else target.class_id
    if role == "teacher" and klass is not None:
        klass.teacher_id = target.id
        target.class_id = klass.id
    if role == "student" and klass is not None and klass.teacher_id == target.id:
        klass.teacher_id = None
    await session.commit()
    return _public_user(target)


@router.get("/v1/school/students")
async def teacher_students(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    if user.role != "teacher":
        raise HTTPException(403, "Добавлять учеников может учитель")
    classes = (
        await session.execute(
            select(ClassGroup).where(ClassGroup.teacher_id == user.id).order_by(ClassGroup.name)
        )
    ).scalars().all()
    class_ids = [row.id for row in classes]
    students = []
    if class_ids:
        rows = (
            await session.execute(
                select(User)
                .where(User.class_id.in_(class_ids), User.role == "student")
                .order_by(User.name, User.username)
            )
        ).scalars().all()
        students = [_public_user(row) for row in rows]
    return {
        "classes": [
            {"id": row.id, "name": row.name, "school_id": row.school_id}
            for row in classes
        ],
        "students": students,
    }


@router.post("/v1/school/students")
async def teacher_add_student(
    payload: AddStudentIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user_v1),
) -> dict:
    if user.role != "teacher":
        raise HTTPException(403, "Добавлять учеников может учитель")
    classes = (
        await session.execute(
            select(ClassGroup).where(ClassGroup.teacher_id == user.id).order_by(ClassGroup.id)
        )
    ).scalars().all()
    if not classes:
        raise HTTPException(400, "Админ ещё не привязал вас к классу")
    klass = next((row for row in classes if row.id == payload.class_id), None) if payload.class_id else classes[0]
    if klass is None:
        raise HTTPException(404, "Этот класс вам не принадлежит")
    student = await _user_by_username(session, payload.username)
    if student.role in ("teacher", "admin"):
        raise HTTPException(400, "Учителя и администратора нельзя записать учеником")
    student.role = "student"
    student.school_id = klass.school_id
    student.class_id = klass.id
    await session.commit()
    return _public_user(student)
