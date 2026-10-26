"""Статистика. Экран #/stats: KPI, кольцевая, столбчатая и линейная диаграммы, таблица команды.
Всё считается из реальных данных: задач и учёта часов (POST /api/worklogs)."""
from collections import defaultdict
from datetime import timedelta

from flask import request

from ..extensions import db
from ..models import BoardColumn, Task, User, WorkLog, today
from ..utils import ApiError, auth_required, search_term
from . import api_bp

PERIOD_DAYS = {"week": 7, "month": 30, "all": None}
BAR_COLORS = ["#c173fe", "#6f6ff6", "#e63246"]
CROWNS = ["red", "blue", "purple"]


@api_bp.get("/stats")
@auth_required
def stats():
    """?period=all|month|week, ?q= — поиск участника в таблице команды."""
    period = request.args.get("period", "all")
    if period not in PERIOD_DAYS:
        raise ApiError("period: all, month или week", 422, {"period": "Неверный период"})
    now = today()
    days = PERIOD_DAYS[period]
    since = now - timedelta(days=days - 1) if days else None

    task_stmt = db.select(Task).join(BoardColumn)
    log_stmt = db.select(WorkLog)
    if since:
        task_stmt = task_stmt.where(db.func.date(Task.created_at) >= since)
        log_stmt = log_stmt.where(WorkLog.day >= since)
    tasks = db.session.scalars(task_stmt).all()
    logs = db.session.scalars(log_stmt).all()

    total_hours = sum(float(l.hours) for l in logs)
    done_tasks = [t for t in tasks if t.column.is_done]

    # Кольцевая диаграмма: задачи по разделам
    columns = db.session.scalars(db.select(BoardColumn).order_by(BoardColumn.position, BoardColumn.id)).all()
    per_col = defaultdict(int)
    for t in tasks:
        per_col[t.column_id] += 1
    distribution = [{"label": c.title, "value": per_col[c.id], "color": c.color} for c in columns]

    # Столбчатая: часы за последние 5 дней, когда была работа
    by_day = defaultdict(float)
    for l in logs:
        by_day[l.day] += float(l.hours)
    last_days = sorted(by_day)[-5:]
    work_hours = [{"label": d.strftime("%d.%m.%y"), "date": d.isoformat(), "value": round(by_day[d], 1),
                   "color": BAR_COLORS[i % len(BAR_COLORS)]} for i, d in enumerate(last_days)]

    # Линейная: активность команды (часы) — по дням для недели/месяца, по неделям (20 шт.) для «всё время»
    if days:
        activity = [round(by_day.get(since + timedelta(days=i), 0.0), 1) for i in range(days)]
        activity_labels = [(since + timedelta(days=i)).strftime("%d.%m") for i in range(days)]
    else:
        start = now - timedelta(weeks=20) + timedelta(days=1)
        buckets = [0.0] * 20
        for d, h in by_day.items():
            idx = (d - start).days // 7
            if 0 <= idx < 20:
                buckets[idx] += h
        activity = [round(b, 1) for b in buckets]
        activity_labels = [(start + timedelta(weeks=i)).strftime("%d.%m") for i in range(20)]

    # Таблица эффективности команды
    hours_by_user = defaultdict(float)
    for l in logs:
        hours_by_user[l.user_id] += float(l.hours)
    tasks_by_user, done_by_user = defaultdict(int), defaultdict(int)
    for t in tasks:
        if t.assignee_id:
            tasks_by_user[t.assignee_id] += 1
            if t.column.is_done:
                done_by_user[t.assignee_id] += 1
    ids = set(hours_by_user) | set(tasks_by_user)
    users = {u.id: u for u in db.session.scalars(db.select(User).where(User.id.in_(ids)))} if ids else {}
    team = []
    for uid, u in users.items():
        team.append({
            "person": uid, "name": u.name, "role": u.team_role or None, "tag": u.department,
            "tasks": tasks_by_user[uid], "done": done_by_user[uid], "hours": round(hours_by_user[uid], 1),
            "share": round(hours_by_user[uid] * 100 / total_hours) if total_hours else 0,
        })
    team.sort(key=lambda m: (m["tasks"], m["hours"]), reverse=True)
    for i, m in enumerate(team):
        m["crown"] = CROWNS[i] if i < 3 else None
        m["color"] = CROWNS[i] if i < 3 else "gray"
    q = search_term()
    if q:
        team = [m for m in team if q in m["name"].lower()]

    return {
        "period": period,
        "hours": round(total_hours),
        "tasks": len(tasks),
        "completion": round(len(done_tasks) * 100 / len(tasks)) if tasks else 0,
        "distribution": distribution,
        "workHours": work_hours,
        "activity": activity,
        "activityLabels": activity_labels,
        "team": team,
    }
