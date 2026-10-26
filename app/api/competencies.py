"""Компетенции и рекомендации. Экран #/competencies (режимы «студент» и «руководитель»), блок навыков в профиле."""
from collections import defaultdict

from flask import request

from ..extensions import db
from ..models import CompetencyTopic, Recommendation, Technology, User
from ..utils import (
    ApiError, attach_files, auth_required, body, current_user, get_or_404, leader_required, opt_str, parse_int,
    parse_user_id, req_str,
)
from . import api_bp


def competencies_of(user_id: int) -> list[dict]:
    """Формат как `myCompetencies`: [{tech, name, percent, topics: [...]}]. percent = доля тем «done»."""
    topics = db.session.scalars(
        db.select(CompetencyTopic).where(CompetencyTopic.user_id == user_id).order_by(CompetencyTopic.id)).all()
    names = {t.id: t.name for t in db.session.scalars(db.select(Technology))}
    grouped: dict[str, list[CompetencyTopic]] = defaultdict(list)
    for t in topics:
        grouped[t.tech_id].append(t)
    result = []
    for tech, items in grouped.items():
        done = sum(1 for t in items if t.status == "done")
        result.append({"tech": tech, "name": names.get(tech, tech), "percent": round(done * 100 / len(items)),
                       "topics": [t.to_dict() for t in items]})
    return result


def _tech(value) -> str:
    if not isinstance(value, str) or db.session.get(Technology, value) is None:
        raise ApiError("Выберите технологию", 422, {"tech": "Нет такой технологии"})
    return value


def _own_topic(topic_id: int) -> CompetencyTopic:
    topic, user = get_or_404(CompetencyTopic, topic_id, "Тема"), current_user()
    if topic.user_id != user.id and not user.is_leader:
        raise ApiError("Нет доступа к этой теме", 403)
    return topic


@api_bp.get("/competencies")
@auth_required
def my_competencies():
    """Компетенции текущего пользователя (или ?user=<id> — для руководителя)."""
    user = current_user()
    uid = user.id
    if request.args.get("user"):
        uid = parse_int(request.args["user"], "user")
        if uid != user.id and not user.is_leader:
            raise ApiError("Чужие компетенции видит только руководитель", 403)
    return competencies_of(uid)


@api_bp.post("/competencies/topics")
@auth_required
def add_topic():
    """«Добавить компетенцию»: {tech, title, notes?, files?: [id]}"""
    data, user = body(), current_user()
    topic = CompetencyTopic(user_id=user.id, tech_id=_tech(data.get("tech")),
                            title=req_str(data, "title", "Тема"), notes=opt_str(data, "notes", ""), status="progress")
    db.session.add(topic)
    db.session.flush()
    attach_files(data.get("files"), user, "topic", topic.id)
    db.session.commit()
    return topic.to_dict(), 201


@api_bp.patch("/competencies/topics/<int:topic_id>")
@auth_required
def update_topic(topic_id: int):
    """{tech?, title?, notes?, status?: progress|done, files?}"""
    topic, data = _own_topic(topic_id), body()
    if "tech" in data:
        topic.tech_id = _tech(data["tech"])
    if "title" in data:
        topic.title = req_str(data, "title", "Тема")
    if "notes" in data:
        topic.notes = opt_str(data, "notes", "")
    if "status" in data:
        if data["status"] not in ("progress", "done"):
            raise ApiError("status: progress или done", 422, {"status": "Неверный статус"})
        topic.status = data["status"]
    attach_files(data.get("files"), current_user(), "topic", topic.id)
    db.session.commit()
    return topic.to_dict()


@api_bp.delete("/competencies/topics/<int:topic_id>")
@auth_required
def delete_topic(topic_id: int):
    from .files import purge
    topic = _own_topic(topic_id)
    purge("topic", topic.id)
    db.session.delete(topic)
    db.session.commit()
    return "", 204


@api_bp.get("/competencies/team")
@leader_required
def team_skills():
    """Навыки команды для руководителя — формат как `teamSkills`."""
    result = []
    for u in db.session.scalars(db.select(User).order_by(User.id)):
        comps = competencies_of(u.id)
        if not comps:
            continue
        result.append({
            "person": u.id, "role": u.team_role or None, "tags": [u.department] if u.department else [],
            "done": sum(1 for c in comps if c["percent"] >= 100), "total": len(comps),
            "skills": [[c["tech"], c["percent"]] for c in comps],
        })
    return result


@api_bp.get("/competencies/departments")
@leader_required
def departments():
    """Отделы и средний уровень участников — формат как `teamDepartments` (без цветов: их считает фронт по %)."""
    groups: dict[str, list] = defaultdict(list)
    for u in db.session.scalars(db.select(User).order_by(User.id)):
        comps = competencies_of(u.id)
        if u.department and comps:
            groups[u.department].append([u.id, round(sum(c["percent"] for c in comps) / len(comps))])
    return [{"name": name, "members": members} for name, members in groups.items()]


# ======================================================================= Рекомендации

@api_bp.get("/recommendations")
@auth_required
def list_recommendations():
    """Мои рекомендации (новые сверху). Руководитель может передать ?to=<id> или ?sent=1."""
    user, args = current_user(), request.args
    stmt = db.select(Recommendation).order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
    if args.get("sent") == "1":
        stmt = stmt.where(Recommendation.author_id == user.id)
    elif args.get("to"):
        uid = parse_int(args["to"], "to")
        if uid != user.id and not user.is_leader:
            raise ApiError("Нет доступа", 403)
        stmt = stmt.where(Recommendation.recipient_id == uid)
    else:
        stmt = stmt.where(Recommendation.recipient_id == user.id)
    return [r.to_dict() for r in db.session.scalars(stmt)]


@api_bp.post("/recommendations")
@leader_required
def add_recommendation():
    """«Добавить рекомендацию»: {to, text, link?: {label, href}, files?: [id]}"""
    data, user = body(), current_user()
    to = parse_user_id(data.get("to"), "to")
    if to is None:
        raise ApiError("Выберите студента", 422, {"to": "Обязательное поле"})
    link = data.get("link") or {}
    if not isinstance(link, dict):
        raise ApiError("link должен быть объектом {label, href}", 422)
    rec = Recommendation(author_id=user.id, recipient_id=to, text=req_str(data, "text", "Рекомендация", max_len=5000),
                         link_label=str(link.get("label") or "")[:255], link_href=str(link.get("href") or "")[:1024])
    db.session.add(rec)
    db.session.flush()
    attach_files(data.get("files"), user, "recommendation", rec.id)
    db.session.commit()
    return rec.to_dict(), 201


@api_bp.post("/recommendations/<int:rec_id>/read")
@auth_required
def read_recommendation(rec_id: int):
    rec = get_or_404(Recommendation, rec_id, "Рекомендация")
    if rec.recipient_id != current_user().id:
        raise ApiError("Нет доступа", 403)
    rec.is_read = True
    db.session.commit()
    return rec.to_dict()


@api_bp.post("/recommendations/read-all")
@auth_required
def read_all_recommendations():
    db.session.execute(db.update(Recommendation).where(Recommendation.recipient_id == current_user().id)
                       .values(is_read=True))
    db.session.commit()
    return {"ok": True}
