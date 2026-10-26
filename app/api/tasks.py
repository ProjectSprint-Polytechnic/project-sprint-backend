"""Канбан-доска: разделы (колонки), задачи, комментарии, дедлайны, учёт часов.
Экраны: #/tasks, #/deadlines, окно задачи, окно комментариев."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from flask import request

from ..extensions import db
from ..models import BoardColumn, Project, Task, TaskComment, User, WorkLog, today, utcnow
from ..utils import (
    ApiError, attach_files, auth_required, body, current_user, get_or_404, leader_required, opt_str, parse_date,
    parse_int, parse_user_id, req_str, search_term, str_list,
)
from . import api_bp

HEX = "0123456789abcdefABCDEF"


def _color(value, key="color") -> str:
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#" or any(c not in HEX for c in value[1:]):
        raise ApiError("Цвет в формате #rrggbb", 422, {key: "Неверный цвет"})
    return value


# ======================================================================= Колонки

@api_bp.get("/columns")
@auth_required
def list_columns():
    cols = db.session.scalars(db.select(BoardColumn).order_by(BoardColumn.position, BoardColumn.id))
    return [c.to_dict() for c in cols]


@api_bp.post("/columns")
@leader_required
def create_column():
    """Новый раздел: {title, color, task?: {...}} — как окно «Новый раздел» (можно сразу с задачей)."""
    data = body()
    last = db.session.scalar(db.select(db.func.max(BoardColumn.position))) or 0
    col = BoardColumn(title=req_str(data, "title", "Название", max_len=128),
                      color=_color(data.get("color", "#727272")), position=last + 1)
    db.session.add(col)
    db.session.flush()
    created_task = None
    if isinstance(data.get("task"), dict) and (data["task"].get("title") or "").strip():
        created_task = _create_task({**data["task"], "column": col.id}, current_user())
    db.session.commit()
    result = col.to_dict()
    if created_task:
        result["task"] = created_task.to_dict()
    return result, 201


@api_bp.patch("/columns/<int:col_id>")
@leader_required
def update_column(col_id: int):
    col, data = get_or_404(BoardColumn, col_id, "Раздел"), body()
    if "title" in data:
        col.title = req_str(data, "title", "Название", max_len=128)
    if "color" in data:
        col.color = _color(data["color"])
    if "position" in data:
        col.position = parse_int(data["position"], "position", 0)
    db.session.commit()
    return col.to_dict()


@api_bp.delete("/columns/<int:col_id>")
@leader_required
def delete_column(col_id: int):
    """Удалить раздел. Если в нём есть задачи — передайте ?moveTo=<id колонки>."""
    col = get_or_404(BoardColumn, col_id, "Раздел")
    if col.key:
        raise ApiError("Базовые разделы удалить нельзя", 422)
    if col.tasks:
        target_id = request.args.get("moveTo")
        if not target_id:
            raise ApiError("В разделе есть задачи — укажите moveTo", 422)
        target = get_or_404(BoardColumn, parse_int(target_id, "moveTo"), "Раздел")
        for t in list(col.tasks):
            _set_column(t, target)
    db.session.delete(col)
    db.session.commit()
    return "", 204


# ======================================================================= Задачи

def _can_edit(task: Task, user: User) -> bool:
    return user.is_leader or user.id in (task.assignee_id, task.author_id)


def _set_column(task: Task, col: BoardColumn) -> None:
    was_done = bool(task.column and task.column.is_done)
    if col.is_done and not was_done:
        task.progress = 100
        task.completed_at = utcnow()
    elif not col.is_done:
        task.completed_at = None
    task.column = col
    task.column_id = col.id


def _apply_task_fields(task: Task, data: dict) -> None:
    if "title" in data:
        task.title = req_str(data, "title", "Название задачи")
    if "description" in data:
        task.description = opt_str(data, "description", "")
    if "notes" in data:
        task.notes = opt_str(data, "notes", "")
    if "assignee" in data:
        task.assignee_id = parse_user_id(data["assignee"], "assignee")
    if "projectId" in data:
        task.project_id = None if data["projectId"] in (None, "") else \
            get_or_404(Project, parse_int(data["projectId"], "projectId"), "Проект").id
    if "start" in data:
        task.start = parse_date(data["start"], "start")
    if "end" in data:
        task.end = parse_date(data["end"], "end")
    if task.start and task.end and task.end < task.start:
        raise ApiError("Дата окончания раньше даты начала", 422, {"end": "Раньше даты начала"})
    if "tags" in data:
        task.tags = str_list(data["tags"], "tags")
    if "position" in data:
        task.position = parse_int(data["position"], "position", 0)
    if "progress" in data:
        task.progress = parse_int(data["progress"], "progress", 0, 100)


def _resolve_column(value) -> BoardColumn:
    """Колонку можно передать числом (id) или ключом: 'progress' | 'plans' | 'done'."""
    if isinstance(value, str) and not value.isdigit():
        col = db.session.scalar(db.select(BoardColumn).where(BoardColumn.key == value))
    else:
        col = db.session.get(BoardColumn, parse_int(value, "column"))
    if col is None:
        raise ApiError("Раздел не найден", 422, {"column": "Нет такого раздела"})
    return col


def _create_task(data: dict, user: User) -> Task:
    col = _resolve_column(data.get("column"))
    task = Task(column=col, column_id=col.id, author_id=user.id, assignee_id=user.id, tags=["Срочное"],
                description="", notes="", progress=0)
    _apply_task_fields(task, data)
    if not task.title:
        raise ApiError("Заполните поле «Название задачи»", 422, {"title": "Обязательное поле"})
    if col.is_done:
        task.progress, task.completed_at = 100, utcnow()
    if not data.get("tags"):
        task.tags = ["Срочное"]
    db.session.add(task)
    db.session.flush()
    attach_files(data.get("files"), user, "task", task.id)
    return task


def _match(task: Task, q: str) -> bool:
    hay = " ".join([task.title, task.description, " ".join(task.tags or [])]).lower()
    return q in hay


@api_bp.get("/tasks")
@auth_required
def list_tasks():
    """Фильтры: ?q= поиск, ?column=<id|key>, ?assignee=<id>|me, ?projectId=, ?done=1|0"""
    stmt = db.select(Task).order_by(Task.position, Task.id)
    args = request.args
    if args.get("column"):
        stmt = stmt.where(Task.column_id == _resolve_column(args["column"]).id)
    if args.get("assignee"):
        uid = current_user().id if args["assignee"] == "me" else parse_int(args["assignee"], "assignee")
        stmt = stmt.where(Task.assignee_id == uid)
    if args.get("projectId"):
        stmt = stmt.where(Task.project_id == parse_int(args["projectId"], "projectId"))
    if args.get("done") in ("0", "1"):
        stmt = stmt.join(BoardColumn).where(BoardColumn.is_done.is_(args["done"] == "1"))
    tasks = db.session.scalars(stmt).all()
    q = search_term()
    return [t.to_dict() for t in tasks if not q or _match(t, q)]


@api_bp.post("/tasks")
@auth_required
def create_task():
    """{column, title, description?, assignee?, start?, end?, tags?, notes?, projectId?, files?: [id]}"""
    task = _create_task(body(), current_user())
    db.session.commit()
    return task.to_dict(), 201


@api_bp.get("/tasks/<int:task_id>")
@auth_required
def get_task(task_id: int):
    return get_or_404(Task, task_id, "Задача").to_dict()


@api_bp.patch("/tasks/<int:task_id>")
@auth_required
def update_task(task_id: int):
    """Любые поля задачи + column (перетаскивание между колонками). Перенос в «Готовые» ставит 100%."""
    task, user, data = get_or_404(Task, task_id, "Задача"), current_user(), body()
    if not _can_edit(task, user):
        raise ApiError("Изменять задачу могут исполнитель, автор или руководитель", 403)
    _apply_task_fields(task, data)
    if "column" in data:
        _set_column(task, _resolve_column(data["column"]))
    attach_files(data.get("files"), user, "task", task.id)
    db.session.commit()
    return task.to_dict()


@api_bp.delete("/tasks/<int:task_id>")
@auth_required
def delete_task(task_id: int):
    task, user = get_or_404(Task, task_id, "Задача"), current_user()
    if not (user.is_leader or task.author_id == user.id):
        raise ApiError("Удалять задачу может руководитель или автор", 403)
    from .files import purge
    purge("task", task.id)
    db.session.delete(task)
    db.session.commit()
    return "", 204


# ======================================================================= Комментарии

@api_bp.get("/tasks/<int:task_id>/comments")
@auth_required
def list_comments(task_id: int):
    task = get_or_404(Task, task_id, "Задача")
    uid = current_user().id
    return [c.to_dict(uid) for c in reversed(task.comments)]  # новые сверху, как в макете


@api_bp.post("/tasks/<int:task_id>/comments")
@auth_required
def add_comment(task_id: int):
    task, user = get_or_404(Task, task_id, "Задача"), current_user()
    c = TaskComment(task=task, author_id=user.id, text=req_str(body(), "text", "Комментарий", max_len=5000))
    db.session.add(c)
    db.session.commit()
    return c.to_dict(user.id), 201


@api_bp.delete("/comments/<int:comment_id>")
@auth_required
def delete_comment(comment_id: int):
    c, user = get_or_404(TaskComment, comment_id, "Комментарий"), current_user()
    if not (user.is_leader or c.author_id == user.id):
        raise ApiError("Удалить можно только свой комментарий", 403)
    db.session.delete(c)
    db.session.commit()
    return "", 204


# ======================================================================= Дедлайны

@api_bp.get("/deadlines")
@auth_required
def deadlines():
    """Невыполненные задачи со сроком: просрочено / ближайшие 7 дней / позже. ?mine=1 — только мои."""
    stmt = (db.select(Task).join(BoardColumn).where(BoardColumn.is_done.is_(False), Task.end.is_not(None))
            .order_by(Task.end, Task.id))
    if request.args.get("mine") == "1":
        stmt = stmt.where(Task.assignee_id == current_user().id)
    q = search_term()
    now = today()
    groups = {"overdue": [], "week": [], "later": []}
    for t in db.session.scalars(stmt):
        if q and not _match(t, q):
            continue
        key = "overdue" if t.end < now else "week" if t.end <= now + timedelta(days=7) else "later"
        groups[key].append(t.to_dict())
    return groups


# ======================================================================= Учёт часов

@api_bp.get("/worklogs")
@auth_required
def list_worklogs():
    """?user=<id>|me (по умолчанию me), ?from=, ?to="""
    args, user = request.args, current_user()
    who = args.get("user", "me")
    uid = user.id if who == "me" else parse_int(who, "user")
    if uid != user.id and not user.is_leader:
        raise ApiError("Чужие часы видит только руководитель", 403)
    stmt = db.select(WorkLog).where(WorkLog.user_id == uid).order_by(WorkLog.day.desc(), WorkLog.id.desc())
    if args.get("from"):
        stmt = stmt.where(WorkLog.day >= parse_date(args["from"], "from"))
    if args.get("to"):
        stmt = stmt.where(WorkLog.day <= parse_date(args["to"], "to"))
    return [w.to_dict() for w in db.session.scalars(stmt)]


@api_bp.post("/worklogs")
@auth_required
def add_worklog():
    """{hours, date?, taskId?, comment?}"""
    data, user = body(), current_user()
    try:
        hours = Decimal(str(data.get("hours")))
    except (InvalidOperation, ValueError):
        raise ApiError("Укажите часы числом", 422, {"hours": "Ожидается число"})
    if not (Decimal("0") < hours <= Decimal("24")):
        raise ApiError("Часы: от 0 до 24", 422, {"hours": "От 0 до 24"})
    task_id = None
    if data.get("taskId") not in (None, ""):
        task_id = get_or_404(Task, parse_int(data["taskId"], "taskId"), "Задача").id
    log = WorkLog(user_id=user.id, task_id=task_id, hours=hours, day=parse_date(data.get("date"), "date") or today(),
                  comment=opt_str(data, "comment", ""))
    db.session.add(log)
    db.session.commit()
    return log.to_dict(), 201


@api_bp.delete("/worklogs/<int:log_id>")
@auth_required
def delete_worklog(log_id: int):
    log, user = get_or_404(WorkLog, log_id, "Запись"), current_user()
    if log.user_id != user.id and not user.is_leader:
        raise ApiError("Нет доступа", 403)
    db.session.delete(log)
    db.session.commit()
    return "", 204
