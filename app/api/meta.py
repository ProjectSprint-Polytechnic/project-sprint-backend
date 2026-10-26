"""Справочники для выпадающих списков: хештеги, цвета разделов, технологии."""
from ..extensions import db
from ..models import Technology
from ..utils import auth_required
from . import api_bp

HASHTAGS = ["Дизайн", "Python", "Программирование", "Статистика", "Отчёты", "Срочное", "Анализ"]

COLUMN_COLORS = [
    {"id": "red", "label": "Красный", "value": "#e63246"},
    {"id": "purple", "label": "Фиолетовый", "value": "#b04bfe"},
    {"id": "blue", "label": "Синий", "value": "#4646f4"},
    {"id": "orange", "label": "Оранжевый", "value": "#ef652a"},
    {"id": "pink", "label": "Розовый", "value": "#ff4fd8"},
    {"id": "yellow", "label": "Жёлтый", "value": "#f2c94c"},
    {"id": "gray", "label": "Серый", "value": "#727272"},
    {"id": "sky", "label": "Голубой", "value": "#039be5"},
]


@api_bp.get("/meta")
@auth_required
def meta():
    techs = db.session.scalars(db.select(Technology).order_by(Technology.name)).all()
    return {"hashtags": HASHTAGS, "columnColors": COLUMN_COLORS, "techs": [t.to_dict() for t in techs]}
