"""Модели базы данных (PostgreSQL).

Ключи в ответах API (camelCase) совпадают с полями из src/data/mock.js фронтенда,
поэтому моки можно заменить ответами сервера почти без переделок.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Table, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

DEFAULT_NOTIFY = {"all": False, "messages": True, "email": False, "tasks": True, "comments": True, "deadlines": True}


APP_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Moscow"))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def local(dt: datetime) -> datetime:
    """Время в часовом поясе приложения (для полей вида «10:16»)."""
    return dt.astimezone(APP_TZ)


def today() -> date:
    return datetime.now(APP_TZ).date()


def iso(d: date | datetime | None) -> str | None:
    return d.isoformat() if d else None


def ru_date(d: date | datetime | None) -> str | None:
    if isinstance(d, datetime):
        d = local(d)
    return d.strftime("%d.%m.%Y") if d else None


# ---------------------------------------------------------------- Пользователи

class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="student")  # student | leader

    name: Mapped[str] = mapped_column(String(128), default="")          # «Иван Иванов»
    full_name: Mapped[str] = mapped_column(String(255), default="")     # «Иван Иванов Иванович»
    phone: Mapped[str] = mapped_column(String(32), default="")
    telegram: Mapped[str] = mapped_column(String(64), default="")
    vk: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(64), default="Учится")
    sex: Mapped[str] = mapped_column(String(16), default="")
    birth: Mapped[date | None] = mapped_column(Date)
    faculty: Mapped[str] = mapped_column(String(255), default="")
    direction: Mapped[str] = mapped_column(String(255), default="")
    course: Mapped[int | None] = mapped_column(Integer)
    department: Mapped[str] = mapped_column(String(128), default="")    # отдел: Аналитика, Бэкенд…
    position: Mapped[str] = mapped_column(String(128), default="Участник")
    team_role: Mapped[str] = mapped_column(String(64), default="")      # «Тим-лидер»
    group: Mapped[str] = mapped_column("group_name", String(32), default="")

    avatar_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id", ondelete="SET NULL", use_alter=True))
    banner: Mapped[int] = mapped_column(Integer, default=0)
    theme: Mapped[str] = mapped_column(String(8), default="light")
    lang: Mapped[str] = mapped_column(String(4), default="ru")
    notify: Mapped[dict] = mapped_column(JSONB, default=lambda: dict(DEFAULT_NOTIFY))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def set_password(self, raw: str) -> None:
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    @property
    def is_leader(self) -> bool:
        return self.role == "leader"

    def to_public(self) -> dict:
        """Краткая карточка — как элемент массива `people` во фронтенде."""
        return {
            "id": self.id,
            "name": self.name or self.login,
            "tag": self.department,
            "role": self.team_role or None,
            "group": self.group,
            "avatar": f"/api/files/{self.avatar_id}" if self.avatar_id else None,
        }

    def to_profile(self) -> dict:
        """Полный профиль — как объект `me` во фронтенде."""
        first_project = next(iter(sorted(self.projects, key=lambda p: p.id)), None)
        return {
            **self.to_public(),
            "login": self.login,
            "accountRole": self.role,
            "fullName": self.full_name,
            "email": self.email or "",
            "phone": self.phone,
            "telegram": self.telegram,
            "vk": self.vk,
            "status": self.status,
            "sex": self.sex,
            "birth": iso(self.birth),
            "faculty": self.faculty,
            "direction": self.direction,
            "course": self.course,
            "project": first_project.title if first_project else "",
            "department": self.department,
            "position": self.position,
            "banner": self.banner,
            "settings": {"theme": self.theme, "lang": self.lang, "notify": {**DEFAULT_NOTIFY, **(self.notify or {})}},
        }


class TokenBlocklist(db.Model):
    """Отозванные JWT (выход из аккаунта)."""
    __tablename__ = "token_blocklist"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- Файлы

class Attachment(db.Model):
    """Загруженный файл. Привязывается к сущности через (target_type, target_id)."""
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    # task | report | topic | message | help | recommendation | avatar
    target_type: Mapped[str | None] = mapped_column(String(32), index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.filename, "size": self.size, "mime": self.mime,
                "url": f"/api/files/{self.id}"}


def attachments_for(target_type: str, target_id: int) -> list[dict]:
    rows = db.session.scalars(
        db.select(Attachment).where(Attachment.target_type == target_type, Attachment.target_id == target_id)
        .order_by(Attachment.id)
    )
    return [a.to_dict() for a in rows]


# ---------------------------------------------------------------- Задачи (канбан)

class BoardColumn(db.Model):
    __tablename__ = "columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str | None] = mapped_column(String(32), unique=True)  # progress | plans | done для базовых колонок
    title: Mapped[str] = mapped_column(String(128))
    color: Mapped[str] = mapped_column(String(16), default="#727272")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)  # перенос сюда = задача выполнена

    tasks: Mapped[list[Task]] = relationship(back_populates="column")

    def to_dict(self) -> dict:
        return {"id": self.id, "key": self.key, "title": self.title, "color": self.color,
                "position": self.position, "isDone": self.is_done}


class Task(db.Model):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    column_id: Mapped[int] = mapped_column(ForeignKey("columns.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    start: Mapped[date | None] = mapped_column(Date)
    end: Mapped[date | None] = mapped_column(Date)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    column: Mapped[BoardColumn] = relationship(back_populates="tasks")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id])
    comments: Mapped[list[TaskComment]] = relationship(back_populates="task", cascade="all, delete-orphan",
                                                       order_by="TaskComment.id")

    @property
    def days_left(self) -> int | None:
        if not self.end:
            return None
        return (self.end - today()).days

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "column": self.column_id,
            "columnKey": self.column.key if self.column else None,
            "title": self.title,
            "description": self.description,
            "progress": self.progress,
            "days": self.days_left,
            "comments": len(self.comments),
            "assignee": self.assignee_id,
            "author": self.author_id,
            "projectId": self.project_id,
            "start": iso(self.start),
            "end": iso(self.end),
            "tags": list(self.tags or []),
            "docs": attachments_for("task", self.id),
            "notes": self.notes,
            "position": self.position,
            "createdAt": iso(self.created_at),
            "completedAt": iso(self.completed_at),
        }


class TaskComment(db.Model):
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    task: Mapped[Task] = relationship(back_populates="comments")

    def to_dict(self, viewer_id: int | None = None) -> dict:
        return {"id": self.id, "taskId": self.task_id, "from": self.author_id, "text": self.text,
                "date": ru_date(self.created_at), "createdAt": iso(self.created_at),
                "mine": self.author_id == viewer_id}


class WorkLog(db.Model):
    """Учёт отработанных часов — источник данных для «Статистики»."""
    __tablename__ = "work_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "userId": self.user_id, "taskId": self.task_id, "date": iso(self.day),
                "hours": float(self.hours), "comment": self.comment}


# ---------------------------------------------------------------- Компетенции

class Technology(db.Model):
    __tablename__ = "technologies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # python, html, figma…
    name: Mapped[str] = mapped_column(String(64))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}


class CompetencyTopic(db.Model):
    """Тема, которую студент изучает в рамках технологии. Процент по технологии = доля тем со статусом done."""
    __tablename__ = "competency_topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tech_id: Mapped[str] = mapped_column(ForeignKey("technologies.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="progress")  # progress | done
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "tech": self.tech_id, "title": self.title, "notes": self.notes,
                "status": self.status, "docs": attachments_for("topic", self.id)}


class Recommendation(db.Model):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    recipient_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    link_label: Mapped[str] = mapped_column(String(255), default="")
    link_href: Mapped[str] = mapped_column(String(1024), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        link = {"label": self.link_label, "href": self.link_href} if (self.link_label or self.link_href) else None
        return {"id": self.id, "from": self.author_id, "to": self.recipient_id, "date": ru_date(self.created_at),
                "createdAt": iso(self.created_at), "text": self.text, "link": link, "isNew": not self.is_read,
                "files": attachments_for("recommendation", self.id)}


# ---------------------------------------------------------------- Проекты

project_members = Table(
    "project_members", db.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Project(db.Model):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), default="progress")  # progress | done
    progress: Mapped[int] = mapped_column(Integer, default=0)
    start: Mapped[date | None] = mapped_column(Date)
    end: Mapped[date | None] = mapped_column(Date)
    goal: Mapped[str] = mapped_column(Text, default="")
    relevance: Mapped[str] = mapped_column(Text, default="")
    problem: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[str] = mapped_column(Text, default="")
    tasks: Mapped[list] = mapped_column(JSONB, default=list)  # «Задачи проекта» из формы — список строк
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[User]] = relationship(secondary=project_members, backref="projects")
    stages: Mapped[list[ProjectStage]] = relationship(back_populates="project", cascade="all, delete-orphan",
                                                      order_by="ProjectStage.position")

    @property
    def days_left(self) -> int:
        if self.status == "done" or not self.end:
            return 0
        return max(0, (self.end - today()).days)

    def to_dict(self, full: bool = True) -> dict:
        data = {
            "id": self.id, "title": self.title, "leader": self.leader_id, "members": len(self.members),
            "daysLeft": self.days_left, "progress": self.progress, "status": self.status,
            "start": iso(self.start), "end": iso(self.end),
        }
        if full:
            data.update({
                "goal": self.goal, "relevance": self.relevance, "problem": self.problem, "result": self.result,
                "tasks": list(self.tasks or []), "memberIds": sorted(u.id for u in self.members),
                "stages": [s.to_dict() for s in self.stages],
            })
        return data


class ProjectStage(db.Model):
    __tablename__ = "project_stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    percent: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="stages")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "percent": self.percent}


# ---------------------------------------------------------------- Отчёты

class Report(db.Model):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def to_dict(self) -> dict:
        return {"id": self.id, "author": self.author_id, "taskId": self.task_id, "title": self.title,
                "date": ru_date(self.created_at), "createdAt": iso(self.created_at), "notes": self.notes,
                "files": attachments_for("report", self.id)}


# ---------------------------------------------------------------- Чаты

class Chat(db.Model):
    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")  # для личных чатов не используется
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list[ChatMember]] = relationship(back_populates="chat", cascade="all, delete-orphan")


class ChatMember(db.Model):
    __tablename__ = "chat_members"
    __table_args__ = (UniqueConstraint("chat_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    last_read_id: Mapped[int] = mapped_column(Integer, default=0)  # id последнего прочитанного сообщения
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chat: Mapped[Chat] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Message(db.Model):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    def to_dict(self, viewer_id: int) -> dict:
        return {"id": self.id, "chatId": self.chat_id, "from": self.author_id, "mine": self.author_id == viewer_id,
                "text": self.text, "time": local(self.created_at).strftime("%H:%M"),
                "createdAt": iso(self.created_at), "files": attachments_for("message", self.id)}


# ---------------------------------------------------------------- Помощь

class HelpRequest(db.Model):
    __tablename__ = "help_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new | in_work | closed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    def to_dict(self) -> dict:
        return {"id": self.id, "userId": self.user_id, "text": self.text, "status": self.status,
                "createdAt": iso(self.created_at), "files": attachments_for("help", self.id)}
