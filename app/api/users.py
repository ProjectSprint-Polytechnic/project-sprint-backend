"""Профиль, настройки, список людей. Экраны: #/profile, окно «Настройки», выпадающие списки людей."""
from ..extensions import db
from ..models import DEFAULT_NOTIFY, User
from ..utils import (
    ApiError, auth_required, body, current_user, get_or_404, leader_required, opt_str, parse_date, parse_int,
    search_term,
)
from . import api_bp

# Поля профиля, которые пользователь может менять сам (ключ API → атрибут модели)
EDITABLE = {
    "name": "name", "fullName": "full_name", "phone": "phone", "telegram": "telegram", "vk": "vk",
    "status": "status", "sex": "sex", "faculty": "faculty", "direction": "direction",
    "department": "department", "position": "position", "group": "group",
}


@api_bp.get("/me")
@auth_required
def me():
    return current_user().to_profile()


@api_bp.patch("/me")
@auth_required
def update_me():
    user, data = current_user(), body()
    for key, attr in EDITABLE.items():
        if key in data:
            setattr(user, attr, opt_str(data, key, "", 255))
    if "birth" in data:
        user.birth = parse_date(data["birth"], "birth")
    if "course" in data:
        user.course = None if data["course"] in (None, "") else parse_int(data["course"], "course", 1, 6)
    if "banner" in data:
        user.banner = parse_int(data["banner"], "banner", 0, 20)
    if "email" in data:
        email = opt_str(data, "email") or None
        if email and db.session.scalar(db.select(User.id).where(
                db.func.lower(User.email) == email.lower(), User.id != user.id)):
            raise ApiError("Такой email уже зарегистрирован", 422, {"email": "Email занят"})
        user.email = email
    if "avatarId" in data:
        from ..models import Attachment
        if data["avatarId"] is None:
            user.avatar_id = None
        else:
            att = get_or_404(Attachment, parse_int(data["avatarId"], "avatarId"), "Файл")
            if att.owner_id != user.id or not att.mime.startswith("image/"):
                raise ApiError("Аватар должен быть вашим изображением", 422, {"avatarId": "Неверный файл"})
            att.target_type, att.target_id = "avatar", user.id
            user.avatar_id = att.id
    db.session.commit()
    return user.to_profile()


@api_bp.patch("/me/settings")
@auth_required
def update_settings():
    """{theme?: light|dark, lang?: ru|en, notify?: {all, messages, email, tasks, comments, deadlines}}"""
    user, data = current_user(), body()
    if "theme" in data:
        if data["theme"] not in ("light", "dark"):
            raise ApiError("theme: light или dark", 422, {"theme": "Неверное значение"})
        user.theme = data["theme"]
    if "lang" in data:
        if data["lang"] not in ("ru", "en"):
            raise ApiError("lang: ru или en", 422, {"lang": "Неверное значение"})
        user.lang = data["lang"]
    if "notify" in data:
        incoming = data["notify"]
        if not isinstance(incoming, dict):
            raise ApiError("notify должен быть объектом", 422)
        notify = {**DEFAULT_NOTIFY, **(user.notify or {})}
        for k, v in incoming.items():
            if k in DEFAULT_NOTIFY:
                notify[k] = bool(v)
        # «Все» включает/выключает всё сразу, как во фронтенде
        if "all" in incoming:
            notify = {k: bool(incoming["all"]) for k in DEFAULT_NOTIFY}
        user.notify = notify
    db.session.commit()
    return user.to_profile()["settings"]


@api_bp.post("/me/password")
@auth_required
def change_password():
    """{oldPassword, newPassword}"""
    user, data = current_user(), body()
    if not user.check_password(data.get("oldPassword") or ""):
        raise ApiError("Неверный текущий пароль", 422, {"oldPassword": "Неверный пароль"})
    new = data.get("newPassword") or ""
    if len(new) < 6:
        raise ApiError("Пароль должен быть не короче 6 символов", 422, {"newPassword": "Минимум 6 символов"})
    user.set_password(new)
    db.session.commit()
    return {"ok": True}


@api_bp.get("/users")
@auth_required
def list_users():
    """Аналог массива `people`. ?q= — поиск по имени, отделу, группе."""
    q = search_term()
    users = db.session.scalars(db.select(User).order_by(User.id)).all()
    if q:
        users = [u for u in users if q in f"{u.name} {u.full_name} {u.department} {u.group}".lower()]
    return [u.to_public() for u in users]


@api_bp.get("/users/<int:user_id>")
@auth_required
def get_user(user_id: int):
    user = get_or_404(User, user_id, "Пользователь")
    data = user.to_profile()
    data.pop("settings", None)
    return data


@api_bp.patch("/users/<int:user_id>/role")
@leader_required
def set_role(user_id: int):
    """Руководитель меняет роль: {role: student|leader, teamRole?: 'Тим-лидер'}"""
    user, data = get_or_404(User, user_id, "Пользователь"), body()
    if "role" in data:
        if data["role"] not in ("student", "leader"):
            raise ApiError("role: student или leader", 422, {"role": "Неверная роль"})
        if user.id == current_user().id and data["role"] != "leader":
            raise ApiError("Нельзя снять роль руководителя с самого себя", 422)
        user.role = data["role"]
    if "teamRole" in data:
        user.team_role = opt_str(data, "teamRole", "", 64)
    db.session.commit()
    return user.to_profile()
