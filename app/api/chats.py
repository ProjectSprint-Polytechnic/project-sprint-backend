"""Сообщения. Экран #/chats: список чатов, переписка, новый чат, поиск, вложения.
Обновление в реальном времени — опросом: GET /chats/<id>/messages?after=<последний id>."""
from datetime import timedelta

from flask import request

from ..extensions import db
from ..models import Chat, ChatMember, Message, Project, User, local, today
from ..utils import (
    ApiError, attach_files, auth_required, body, current_user, get_or_404, opt_str, parse_int, search_term,
)
from . import api_bp

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _short_time(dt) -> str:
    """Как в списке чатов: «10:16», «Вчера», «Пн», «01.03»."""
    d = local(dt)
    now = today()
    if d.date() == now:
        return d.strftime("%H:%M")
    if d.date() == now - timedelta(days=1):
        return "Вчера"
    if d.date() > now - timedelta(days=7):
        return WEEKDAYS[d.weekday()]
    return d.strftime("%d.%m")


def _membership(chat_id: int, user_id: int) -> ChatMember:
    m = db.session.scalar(db.select(ChatMember).where(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id))
    if m is None:
        raise ApiError("Чат не найден", 404)
    return m


def chat_to_dict(chat: Chat, me: User) -> dict:
    my = next((m for m in chat.members if m.user_id == me.id), None)
    other = None if chat.is_group else next((m.user for m in chat.members if m.user_id != me.id), None)
    last = db.session.scalar(db.select(Message).where(Message.chat_id == chat.id).order_by(Message.id.desc()).limit(1))
    unread = db.session.scalar(db.select(db.func.count(Message.id)).where(
        Message.chat_id == chat.id, Message.id > (my.last_read_id if my else 0), Message.author_id != me.id)) or 0
    title = chat.title if chat.is_group else (other.name if other else chat.title or "Личный чат")
    last_text = "Чат создан"
    if last:
        last_text = last.text or "📎 Вложение"
    return {
        "id": chat.id, "title": title, "isGroup": chat.is_group, "members": len(chat.members),
        "memberIds": sorted(m.user_id for m in chat.members), "person": other.id if other else None,
        "projectId": chat.project_id, "last": last_text,
        "time": _short_time(last.created_at if last else chat.created_at),
        "lastAt": (last.created_at if last else chat.created_at).isoformat(), "unread": unread,
    }


@api_bp.get("/chats")
@auth_required
def list_chats():
    """Мои чаты, свежие сверху. ?q= поиск по названию."""
    me = current_user()
    chats = db.session.scalars(db.select(Chat).join(ChatMember).where(ChatMember.user_id == me.id)).unique().all()
    items = [chat_to_dict(c, me) for c in chats]
    q = search_term()
    if q:
        items = [c for c in items if q in c["title"].lower() or q in c["last"].lower()]
    items.sort(key=lambda c: c["lastAt"], reverse=True)
    return items


@api_bp.post("/chats")
@auth_required
def create_chat():
    """Личный: {person: <id>} — если чат уже есть, вернётся существующий (200).
    Групповой: {title, isGroup: true, members: [id]}. Чат проекта: {projectId} — участники берутся из проекта."""
    data, me = body(), current_user()
    if data.get("person") not in (None, ""):
        other = get_or_404(User, parse_int(data["person"], "person"), "Пользователь")
        if other.id == me.id:
            raise ApiError("Нельзя создать чат с самим собой", 422)
        existing = db.session.scalars(
            db.select(Chat).where(Chat.is_group.is_(False))
            .where(Chat.id.in_(db.select(ChatMember.chat_id).where(ChatMember.user_id == me.id)))
            .where(Chat.id.in_(db.select(ChatMember.chat_id).where(ChatMember.user_id == other.id)))
        ).first()
        if existing:
            return chat_to_dict(existing, me), 200
        chat = Chat(is_group=False, created_by=me.id)
        chat.members = [ChatMember(user_id=me.id), ChatMember(user_id=other.id)]
    elif data.get("projectId") not in (None, ""):
        project = get_or_404(Project, parse_int(data["projectId"], "projectId"), "Проект")
        if not (me.is_leader or any(u.id == me.id for u in project.members)):
            raise ApiError("Вы не участник проекта", 403)
        existing = db.session.scalar(db.select(Chat).where(Chat.project_id == project.id))
        if existing:
            if not any(m.user_id == me.id for m in existing.members):
                existing.members.append(ChatMember(user_id=me.id))
                db.session.commit()
            return chat_to_dict(existing, me), 200
        ids = {u.id for u in project.members} | {me.id}
        chat = Chat(is_group=True, title=project.title, project_id=project.id, created_by=me.id)
        chat.members = [ChatMember(user_id=i) for i in sorted(ids)]
    else:
        title = (opt_str(data, "title") or "").strip() or "Новая группа"
        raw = data.get("members") or []
        if not isinstance(raw, list):
            raise ApiError("members — список id", 422, {"members": "Ожидается список"})
        ids = {parse_int(i, "members") for i in raw} | {me.id}
        found = set(db.session.scalars(db.select(User.id).where(User.id.in_(ids))))
        if found != ids:
            raise ApiError("Не все участники найдены", 422, {"members": "Неизвестный пользователь"})
        chat = Chat(is_group=True, title=title[:255], created_by=me.id)
        chat.members = [ChatMember(user_id=i) for i in sorted(ids)]
    db.session.add(chat)
    db.session.commit()
    return chat_to_dict(chat, me), 201


@api_bp.get("/chats/<int:chat_id>")
@auth_required
def get_chat(chat_id: int):
    me = current_user()
    _membership(chat_id, me.id)
    return chat_to_dict(db.session.get(Chat, chat_id), me)


@api_bp.patch("/chats/<int:chat_id>")
@auth_required
def update_chat(chat_id: int):
    """Групповой чат: {title?, addMembers?: [id], removeMembers?: [id]}"""
    me, data = current_user(), body()
    _membership(chat_id, me.id)
    chat = db.session.get(Chat, chat_id)
    if not chat.is_group:
        raise ApiError("Личный чат нельзя изменить", 422)
    if "title" in data:
        chat.title = (opt_str(data, "title") or chat.title)[:255]
    present = {m.user_id for m in chat.members}
    for uid in data.get("addMembers") or []:
        uid = parse_int(uid, "addMembers")
        get_or_404(User, uid, "Пользователь")
        if uid not in present:
            chat.members.append(ChatMember(user_id=uid))
            present.add(uid)
    remove = {parse_int(u, "removeMembers") for u in data.get("removeMembers") or []}
    chat.members = [m for m in chat.members if m.user_id not in remove]
    db.session.commit()
    return chat_to_dict(chat, me)


@api_bp.post("/chats/<int:chat_id>/leave")
@auth_required
def leave_chat(chat_id: int):
    db.session.delete(_membership(chat_id, current_user().id))
    db.session.commit()
    return "", 204


@api_bp.get("/chats/<int:chat_id>/messages")
@auth_required
def list_messages(chat_id: int):
    """?after=<id> — только новые (для опроса), ?before=<id>&limit=50 — подгрузка истории, ?q= поиск в чате.
    Открытие переписки отмечает сообщения прочитанными."""
    me = current_user()
    member = _membership(chat_id, me.id)
    args = request.args
    limit = parse_int(args.get("limit", 100), "limit", 1, 500)
    stmt = db.select(Message).where(Message.chat_id == chat_id)
    if args.get("after"):
        stmt = stmt.where(Message.id > parse_int(args["after"], "after"))
    if args.get("before"):
        stmt = stmt.where(Message.id < parse_int(args["before"], "before"))
    q = search_term()
    if q:
        stmt = stmt.where(Message.text.ilike(f"%{q}%"))
    msgs = list(reversed(db.session.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all()))
    if msgs and msgs[-1].id > member.last_read_id and not q:
        member.last_read_id = msgs[-1].id
        db.session.commit()
    return [m.to_dict(me.id) for m in msgs]


@api_bp.post("/chats/<int:chat_id>/messages")
@auth_required
def send_message(chat_id: int):
    """{text?, files?: [id]} — нужен текст или хотя бы один файл."""
    me, data = current_user(), body()
    member = _membership(chat_id, me.id)
    text = (opt_str(data, "text", "", 10000) or "")
    if not text and not data.get("files"):
        raise ApiError("Пустое сообщение", 422, {"text": "Введите сообщение"})
    msg = Message(chat_id=chat_id, author_id=me.id, text=text)
    db.session.add(msg)
    db.session.flush()
    attach_files(data.get("files"), me, "message", msg.id)
    member.last_read_id = msg.id
    db.session.commit()
    return msg.to_dict(me.id), 201


@api_bp.post("/chats/<int:chat_id>/read")
@auth_required
def mark_read(chat_id: int):
    member = _membership(chat_id, current_user().id)
    last = db.session.scalar(db.select(db.func.max(Message.id)).where(Message.chat_id == chat_id)) or 0
    member.last_read_id = max(member.last_read_id, last)
    db.session.commit()
    return {"ok": True}


@api_bp.get("/chats/unread")
@auth_required
def unread_total():
    """Общее число непрочитанных — для значка у пункта «Сообщения»."""
    me = current_user()
    total = 0
    for m in db.session.scalars(db.select(ChatMember).where(ChatMember.user_id == me.id)):
        total += db.session.scalar(db.select(db.func.count(Message.id)).where(
            Message.chat_id == m.chat_id, Message.id > m.last_read_id, Message.author_id != me.id)) or 0
    return {"unread": total}
