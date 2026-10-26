"""Бэкенд «Политех»: Flask + PostgreSQL. Точка входа — create_app()."""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import cors, db, jwt, migrate
from .models import TokenBlocklist
from .utils import ApiError

load_dotenv()


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
                  expose_headers=["Content-Disposition"])

    _register_jwt_callbacks()
    _register_errors(app)

    from .api import api_bp
    app.register_blueprint(api_bp)

    from .seed import register_cli
    register_cli(app)

    @app.get("/api/health")
    def health():
        db.session.execute(db.text("select 1"))
        return {"status": "ok"}

    return app


def _register_jwt_callbacks():
    @jwt.token_in_blocklist_loader
    def is_revoked(_header, payload):
        return db.session.scalar(db.select(TokenBlocklist.id).where(TokenBlocklist.jti == payload["jti"])) is not None

    def err(msg, status=401):
        return jsonify(error=msg), status

    jwt.expired_token_loader(lambda h, p: err("Сессия истекла, войдите снова"))
    jwt.invalid_token_loader(lambda reason: err("Неверный токен"))
    jwt.unauthorized_loader(lambda reason: err("Требуется авторизация"))
    jwt.revoked_token_loader(lambda h, p: err("Токен отозван, войдите снова"))
    jwt.needs_fresh_token_loader(lambda h, p: err("Нужен свежий вход"))


def _register_errors(app: Flask):
    @app.errorhandler(ApiError)
    def api_error(e: ApiError):
        return e.to_response()

    @app.errorhandler(JWTExtendedException)
    @app.errorhandler(PyJWTError)
    def jwt_error(e):
        return {"error": "Требуется авторизация"}, 401

    @app.errorhandler(HTTPException)
    def http_error(e: HTTPException):
        messages = {404: "Не найдено", 405: "Метод не поддерживается", 413: "Файл слишком большой"}
        return {"error": messages.get(e.code, e.description)}, e.code

    @app.errorhandler(Exception)
    def unhandled(e: Exception):
        app.logger.exception(e)
        db.session.rollback()
        return {"error": "Внутренняя ошибка сервера"}, 500
