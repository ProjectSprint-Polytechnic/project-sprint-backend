"""Общие помощники: ошибки, разбор тела запроса, текущий пользователь, права."""
from __future__ import annotations

from datetime import date, datetime
from functools import wraps
from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from .extensions import db
from .models import Attachment, User


class ApiError(Exception):
    """Ошибка, которая превращается в JSON-ответ {"error": ..., "fields": {...}}."""

    def __init__(self, message: str, status: int = 400, fields: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.fields = fields or {}

    def to_response(self):
        body: dict[str, Any] = {"error": self.message}
        if self.fields:
            body["fields"] = self.fields
        return body, self.status


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ApiError("Ожидается JSON-объект")
    return data


def current_user() -> User:
    uid = get_jwt_identity()
    user = db.session.get(User, int(uid)) if uid is not None else None
    if user is None:
        raise ApiError("Пользователь не найден", 401)
    return user


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        return fn(*args, **kwargs)
    return wrapper


def leader_required(fn):
    """Доступ только для роли «Руководитель»."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        if not current_user().is_leader:
            raise ApiError("Действие доступно только руководителю", 403)
        return fn(*args, **kwargs)
    return wrapper


def get_or_404(model, ident, what: str = "Объект"):
    obj = db.session.get(model, ident)
    if obj is None:
        raise ApiError(f"{what} не найден", 404)
    return obj


# ---------- разбор полей

def req_str(data: dict, key: str, label: str, min_len: int = 1, max_len: int = 255) -> str:
    value = data.get(key)
    if not isinstance(value, str) or len(value.strip()) < min_len:
        msg = f"Заполните поле «{label}»" if min_len <= 1 else f"«{label}»: минимум {min_len} символа"
        raise ApiError(msg, 422, {key: msg})
    value = value.strip()
    if len(value) > max_len:
        raise ApiError(f"«{label}»: максимум {max_len} символов", 422, {key: "Слишком длинное значение"})
    return value


def opt_str(data: dict, key: str, default: str | None = None, max_len: int = 10000) -> str | None:
    if key not in data or data[key] is None:
        return default
    if not isinstance(data[key], str):
        raise ApiError(f"Поле {key} должно быть строкой", 422, {key: "Ожидается строка"})
    return data[key].strip()[:max_len]


def parse_date(value: Any, key: str = "date") -> date | None:
    """Принимает 'YYYY-MM-DD' или 'DD.MM.YYYY'. Пустое значение → None."""
    if value in (None, ""):
        return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value.strip()[:10], fmt).date()
            except ValueError:
                continue
    raise ApiError("Неверный формат даты (ожидается ГГГГ-ММ-ДД)", 422, {key: "Неверная дата"})


def parse_int(value: Any, key: str, lo: int | None = None, hi: int | None = None) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"Поле {key} должно быть числом", 422, {key: "Ожидается число"})
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise ApiError(f"Поле {key} вне допустимого диапазона", 422, {key: f"Допустимо от {lo} до {hi}"})
    return n


def parse_user_id(value: Any, key: str) -> int | None:
    if value in (None, ""):
        return None
    uid = parse_int(value, key)
    if db.session.get(User, uid) is None:
        raise ApiError("Пользователь не найден", 422, {key: "Нет такого пользователя"})
    return uid


def str_list(value: Any, key: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ApiError(f"Поле {key} должно быть списком строк", 422, {key: "Ожидается список строк"})
    return [v.strip() for v in value if v.strip()]


def attach_files(file_ids: Any, owner: User, target_type: str, target_id: int) -> None:
    """Привязывает ранее загруженные (POST /api/files) файлы к сущности."""
    if not file_ids:
        return
    if not isinstance(file_ids, list):
        raise ApiError("files должно быть списком id файлов", 422, {"files": "Ожидается список"})
    for fid in file_ids:
        att = db.session.get(Attachment, parse_int(fid, "files"))
        if att is None or att.owner_id != owner.id:
            raise ApiError("Файл не найден", 422, {"files": f"Файл {fid} не найден"})
        if att.target_type and (att.target_type, att.target_id) != (target_type, target_id):
            raise ApiError("Файл уже прикреплён к другому объекту", 422, {"files": f"Файл {fid} уже используется"})
        att.target_type, att.target_id = target_type, target_id


def search_term() -> str:
    return (request.args.get("q") or "").strip().lower()
