"""Отчёты по выполненным задачам. Экран #/reports («Выполненные задачи», «Мои отчёты»)."""
from flask import request

from ..extensions import db
from ..models import Report, Task
from ..utils import (
    ApiError, attach_files, auth_required, body, current_user, get_or_404, opt_str, parse_int, search_term,
)
from . import api_bp


@api_bp.get("/reports")
@auth_required
def list_reports():
    """По умолчанию — мои отчёты. ?all=1 — все (для руководителя), ?q= поиск."""
    user = current_user()
    stmt = db.select(Report).order_by(Report.created_at.desc(), Report.id.desc())
    if not (request.args.get("all") == "1" and user.is_leader):
        stmt = stmt.where(Report.author_id == user.id)
    reports = db.session.scalars(stmt).all()
    q = search_term()
    if q:
        reports = [r for r in reports if q in f"{r.title} {r.notes}".lower()]
    return [r.to_dict() for r in reports]


@api_bp.post("/reports")
@auth_required
def create_report():
    """{taskId, notes?, files?: [id]} — название берётся из задачи."""
    data, user = body(), current_user()
    if data.get("taskId") in (None, ""):
        raise ApiError("Выберите выполненную задачу", 422, {"taskId": "Обязательное поле"})
    task = get_or_404(Task, parse_int(data["taskId"], "taskId"), "Задача")
    report = Report(author_id=user.id, task_id=task.id, title=task.title, notes=opt_str(data, "notes", ""))
    db.session.add(report)
    db.session.flush()
    attach_files(data.get("files"), user, "report", report.id)
    db.session.commit()
    return report.to_dict(), 201


def _own(report_id: int) -> Report:
    report, user = get_or_404(Report, report_id, "Отчёт"), current_user()
    if report.author_id != user.id and not user.is_leader:
        raise ApiError("Нет доступа к отчёту", 403)
    return report


@api_bp.get("/reports/<int:report_id>")
@auth_required
def get_report(report_id: int):
    return _own(report_id).to_dict()


@api_bp.patch("/reports/<int:report_id>")
@auth_required
def update_report(report_id: int):
    report, data = _own(report_id), body()
    if "notes" in data:
        report.notes = opt_str(data, "notes", "")
    attach_files(data.get("files"), current_user(), "report", report.id)
    db.session.commit()
    return report.to_dict()


@api_bp.delete("/reports/<int:report_id>")
@auth_required
def delete_report(report_id: int):
    from .files import purge
    report = _own(report_id)
    purge("report", report.id)
    db.session.delete(report)
    db.session.commit()
    return "", 204
