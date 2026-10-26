"""Вход, регистрация, обновление и отзыв токенов. Экран: #/login, #/register."""
import re

from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt, get_jwt_identity, jwt_required

from ..extensions import db
from ..models import TokenBlocklist, User
from ..utils import ApiError, body, current_user, opt_str
from . import api_bp

LOGIN_RE = re.compile(r"^[A-Za-z0-9_.@-]+$")


def _tokens(user: User, remember: bool = True) -> dict:
    data = {"accessToken": create_access_token(identity=str(user.id), additional_claims={"role": user.role}),
            "user": user.to_profile()}
    if remember:
        data["refreshToken"] = create_refresh_token(identity=str(user.id))
    return data


@api_bp.post("/auth/register")
def register():
    """{login, password, password2?, name?, email?} — те же проверки, что во фронтенде."""
    data = body()
    login = (data.get("login") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password2", password)
    errors = {}
    if not login:
        errors["login"] = "Введите логин"
    elif len(login) < 3:
        errors["login"] = "Логин должен быть не короче 3 символов"
    elif len(login) > 64 or not LOGIN_RE.match(login):
        errors["login"] = "Логин: латиница, цифры и символы _ . @ -"
    if not password:
        errors["pass"] = "Введите пароль"
    elif len(password) < 6:
        errors["pass"] = "Пароль должен быть не короче 6 символов"
    if password != password2:
        errors["pass2"] = "Пароли не совпадают"
    email = opt_str(data, "email") or None
    if not errors:
        if db.session.scalar(db.select(User.id).where(db.func.lower(User.login) == login.lower())):
            errors["login"] = "Такой логин уже занят"
        elif email and db.session.scalar(db.select(User.id).where(db.func.lower(User.email) == email.lower())):
            errors["email"] = "Такой email уже зарегистрирован"
    if errors:
        raise ApiError(next(iter(errors.values())), 422, errors)

    user = User(login=login, email=email, name=opt_str(data, "name") or login, role="student")
    user.full_name = user.name
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return _tokens(user), 201


@api_bp.post("/auth/login")
def login():
    """{login, password, remember?}. В поле login можно ввести логин или email."""
    data = body()
    ident = (data.get("login") or "").strip()
    password = data.get("password") or ""
    errors = {}
    if not ident:
        errors["login"] = "Введите логин"
    if not password:
        errors["pass"] = "Введите пароль"
    if errors:
        raise ApiError(next(iter(errors.values())), 422, errors)
    user = db.session.scalar(db.select(User).where(
        db.or_(db.func.lower(User.login) == ident.lower(), db.func.lower(User.email) == ident.lower())))
    if user is None or not user.check_password(password):
        raise ApiError("Неверный логин или пароль", 401, {"pass": "Неверный логин или пароль"})
    return _tokens(user, remember=bool(data.get("remember", True)))


@api_bp.post("/auth/refresh")
@jwt_required(refresh=True)
def refresh():
    """Новый access-токен по refresh-токену (заголовок Authorization: Bearer <refresh>)."""
    user = current_user()
    return {"accessToken": create_access_token(identity=str(user.id), additional_claims={"role": user.role})}


@api_bp.post("/auth/logout")
@jwt_required(verify_type=False)
def logout():
    """Отзывает текущий токен. Чтобы отозвать и refresh, передайте его в теле: {refreshToken}."""
    db.session.add(TokenBlocklist(jti=get_jwt()["jti"]))
    refresh_token = body().get("refreshToken")
    if refresh_token:
        from flask_jwt_extended import decode_token
        try:
            payload = decode_token(refresh_token, allow_expired=True)
            if payload.get("sub") == get_jwt_identity():
                db.session.add(TokenBlocklist(jti=payload["jti"]))
        except Exception:  # noqa: BLE001 — битый refresh просто игнорируем
            pass
    db.session.commit()
    return {"ok": True}


@api_bp.post("/auth/restore")
def restore():
    """Кнопка «Восстановить». Почтового сервера пока нет — заявка принимается, ответ одинаковый
    для существующих и несуществующих логинов (чтобы нельзя было перебирать пользователей)."""
    if not (body().get("login") or "").strip():
        raise ApiError("Введите логин или email", 422, {"login": "Введите логин или email"})
    return {"ok": True, "message": "Если такой пользователь есть, инструкция отправлена на его почту"}
