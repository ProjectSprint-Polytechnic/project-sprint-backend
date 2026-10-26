from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Импорт модулей регистрирует маршруты на api_bp
from . import (  # noqa: E402,F401
    auth, users, meta, tasks, competencies, projects, reports, chats, stats, files,
)
