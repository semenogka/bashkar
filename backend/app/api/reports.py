"""Отчёты преподавателя (LMS): /api/reports/class/{class_id}."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_role
from app.db.base import get_session
from app.models import Answer, ClassGroup, School, User

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/class/{class_id}")
async def class_report(
    class_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(require_role("teacher", "admin", "expert")),
) -> dict:
    klass = await session.get(ClassGroup, class_id)
    if klass is None:
        raise HTTPException(404, "Class not found")
    school = await session.get(School, klass.school_id) if klass.school_id else None
    students = (
        await session.execute(select(User).where(User.class_id == class_id))
    ).scalars().all()

    out_students = []
    total_points = 0
    total_tasks = 0
    accuracies = []
    for u in students:
        answers = (
            await session.execute(select(Answer).where(Answer.user_id == u.id))
        ).scalars().all()
        done = len(answers)
        matched = sum(1 for a in answers if a.matched_consensus)
        acc = (matched / done * 100) if done else 0.0
        out_students.append({
            "user_id": u.id,
            "username": u.username,
            "points": u.points,
            "level": u.level or 1,
            "tasks_done": done,
            "accuracy": round(acc, 1),
        })
        total_points += u.points
        total_tasks += done
        accuracies.append(acc)

    return {
        "class_id": klass.id,
        "class_name": klass.name,
        "school": school.name if school else None,
        "students": out_students,
        "total_points": total_points,
        "total_tasks": total_tasks,
        "avg_accuracy": round(sum(accuracies) / len(accuracies), 1) if accuracies else 0.0,
    }
