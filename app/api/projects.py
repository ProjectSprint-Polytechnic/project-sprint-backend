"""Проекты. Экран #/projects: доска проектов, «Подробнее», добавление и редактирование."""
from flask import request

from ..extensions import db
from ..models import Project, ProjectStage, User
from ..utils import (
    ApiError, auth_required, body, current_user, get_or_404, leader_required, opt_str, parse_date, parse_int,
    parse_user_id, req_str, search_term, str_list,
)
from . import api_bp


def _apply(project: Project, data: dict) -> None:
    if "title" in data:
        project.title = req_str(data, "title", "Название проекта")
    for key in ("goal", "relevance", "problem", "result"):
        if key in data:
            setattr(project, key, opt_str(data, key, ""))
    if "tasks" in data:
        project.tasks = str_list(data["tasks"], "tasks")
    if "leader" in data:
        project.leader_id = parse_user_id(data["leader"], "leader")
    if "start" in data:
        project.start = parse_date(data["start"], "start")
    if "end" in data:
        project.end = parse_date(data["end"], "end")
    if project.start and project.end and project.end < project.start:
        raise ApiError("Дата окончания раньше даты начала", 422, {"end": "Раньше даты начала"})
    if "progress" in data:
        project.progress = parse_int(data["progress"], "progress", 0, 100)
    if "status" in data:
        if data["status"] not in ("progress", "done"):
            raise ApiError("status: progress или done", 422, {"status": "Неверный статус"})
        project.status = data["status"]
        if project.status == "done":
            project.progress = 100
    if "members" in data:
        ids = data["members"]
        if not isinstance(ids, list):
            raise ApiError("members — список id пользователей", 422, {"members": "Ожидается список"})
        users = db.session.scalars(db.select(User).where(User.id.in_([parse_int(i, "members") for i in ids]))).all()
        if len(users) != len(set(ids)):
            raise ApiError("Не все участники найдены", 422, {"members": "Неизвестный пользователь"})
        project.members = list(users)
    if project.leader_id and all(u.id != project.leader_id for u in project.members):
        project.members.append(db.session.get(User, project.leader_id))
    if "stages" in data:
        stages = data["stages"]
        if not isinstance(stages, list):
            raise ApiError("stages — список {name, percent}", 422)
        project.stages = [
            ProjectStage(name=req_str(s, "name", "Этап"), percent=parse_int(s.get("percent", 0), "percent", 0, 100),
                         position=i)
            for i, s in enumerate(stages) if isinstance(s, dict)
        ]


@api_bp.get("/projects")
@auth_required
def list_projects():
    """?status=progress|done, ?q=, ?mine=1 (где я участник). Список — краткий формат, детали в GET /projects/<id>."""
    stmt = db.select(Project).order_by(Project.created_at.desc(), Project.id.desc())
    if request.args.get("status") in ("progress", "done"):
        stmt = stmt.where(Project.status == request.args["status"])
    projects = db.session.scalars(stmt).all()
    if request.args.get("mine") == "1":
        uid = current_user().id
        projects = [p for p in projects if any(u.id == uid for u in p.members)]
    q = search_term()
    if q:
        projects = [p for p in projects if q in f"{p.title} {p.goal}".lower()]
    full = request.args.get("full") == "1"
    return [p.to_dict(full=full) for p in projects]


@api_bp.get("/projects/<int:project_id>")
@auth_required
def get_project(project_id: int):
    return get_or_404(Project, project_id, "Проект").to_dict()


@api_bp.post("/projects")
@leader_required
def create_project():
    """{title, goal?, relevance?, problem?, tasks?: [str], result?, members?: [id], leader?, start?, end?, stages?}"""
    data = body()
    project = Project(title="", status="progress", progress=0, tasks=[], leader_id=current_user().id, members=[])
    db.session.add(project)
    _apply(project, {"title": data.get("title"), **data})
    db.session.commit()
    return project.to_dict(), 201


@api_bp.patch("/projects/<int:project_id>")
@auth_required
def update_project(project_id: int):
    project, user = get_or_404(Project, project_id, "Проект"), current_user()
    if not (user.is_leader or project.leader_id == user.id):
        raise ApiError("Редактировать проект может руководитель или тим-лидер проекта", 403)
    _apply(project, body())
    db.session.commit()
    return project.to_dict()


@api_bp.delete("/projects/<int:project_id>")
@leader_required
def delete_project(project_id: int):
    db.session.delete(get_or_404(Project, project_id, "Проект"))
    db.session.commit()
    return "", 204
