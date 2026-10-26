"""Загрузка и скачивание файлов + форма «Помощь».

Как прикрепить файл к отчёту/задаче/сообщению:
  1) POST /api/files (multipart/form-data, поле file) → {id, name, url}
  2) передать id в поле files при создании: POST /api/reports {taskId, notes, files: [id]}
"""
import mimetypes
import os
import uuid

from flask import current_app, request, send_from_directory
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Attachment, HelpRequest
from ..utils import ApiError, attach_files, auth_required, body, current_user, get_or_404, req_str
from . import api_bp

BLOCKED_EXT = {".exe", ".bat", ".cmd", ".sh", ".js", ".msi", ".com", ".scr", ".html", ".htm", ".svg"}


def _save(storage, owner_id: int) -> Attachment:
    original = (storage.filename or "file").replace("\\", "/").rsplit("/", 1)[-1][:255] or "file"
    ext = os.path.splitext(secure_filename(original) or original)[1].lower()
    if ext in BLOCKED_EXT:
        raise ApiError(f"Файлы {ext} загружать нельзя", 422, {"file": "Недопустимый тип файла"})
    stored = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored)
    storage.save(path)
    mime = storage.mimetype or mimetypes.guess_type(original)[0] or "application/octet-stream"
    att = Attachment(owner_id=owner_id, filename=original, stored_name=stored, mime=mime, size=os.path.getsize(path))
    db.session.add(att)
    return att


@api_bp.post("/files")
@auth_required
def upload():
    """multipart/form-data: поле file (один) или files (несколько). Ответ — объект или список."""
    user = current_user()
    many = request.files.getlist("files")
    one = request.files.get("file")
    if not many and not one:
        raise ApiError("Файл не передан (поле file)", 422, {"file": "Выберите файл"})
    saved = [_save(f, user.id) for f in (many or [one])]
    db.session.commit()
    result = [a.to_dict() for a in saved]
    return (result if many else result[0]), 201


@api_bp.get("/files/<int:file_id>")
@auth_required
def download(file_id: int):
    """Скачать файл (нужен заголовок Authorization). ?inline=1 — открыть в браузере (картинки, PDF)."""
    att = get_or_404(Attachment, file_id, "Файл")
    inline = request.args.get("inline") == "1"
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], att.stored_name, mimetype=att.mime,
                               as_attachment=not inline, download_name=att.filename)


@api_bp.delete("/files/<int:file_id>")
@auth_required
def delete_file(file_id: int):
    att, user = get_or_404(Attachment, file_id, "Файл"), current_user()
    if att.owner_id != user.id and not user.is_leader:
        raise ApiError("Удалить можно только свой файл", 403)
    remove_file(att)
    db.session.commit()
    return "", 204


def remove_file(att: Attachment) -> None:
    try:
        os.remove(os.path.join(current_app.config["UPLOAD_FOLDER"], att.stored_name))
    except FileNotFoundError:
        pass
    db.session.delete(att)


def purge(target_type: str, target_id: int) -> None:
    """Удаляет файлы, привязанные к удаляемой сущности."""
    for att in db.session.scalars(db.select(Attachment).where(
            Attachment.target_type == target_type, Attachment.target_id == target_id)).all():
        remove_file(att)


# ======================================================================= Помощь

@api_bp.post("/help")
@auth_required
def create_help():
    """Окно «Помощь»: {text, files?: [id]} → «Уже решаем вашу проблему!»"""
    data, user = body(), current_user()
    req = HelpRequest(user_id=user.id, text=req_str(data, "text", "Опишите проблему", max_len=10000))
    db.session.add(req)
    db.session.flush()
    attach_files(data.get("files"), user, "help", req.id)
    db.session.commit()
    return req.to_dict(), 201


@api_bp.get("/help")
@auth_required
def list_help():
    """Руководитель видит все обращения, остальные — свои."""
    user = current_user()
    stmt = db.select(HelpRequest).order_by(HelpRequest.id.desc())
    if not user.is_leader:
        stmt = stmt.where(HelpRequest.user_id == user.id)
    return [h.to_dict() for h in db.session.scalars(stmt)]


@api_bp.patch("/help/<int:req_id>")
@auth_required
def update_help(req_id: int):
    user = current_user()
    if not user.is_leader:
        raise ApiError("Доступно только руководителю", 403)
    req, data = get_or_404(HelpRequest, req_id, "Обращение"), body()
    if data.get("status") not in ("new", "in_work", "closed"):
        raise ApiError("status: new, in_work или closed", 422, {"status": "Неверный статус"})
    req.status = data["status"]
    db.session.commit()
    return req.to_dict()
