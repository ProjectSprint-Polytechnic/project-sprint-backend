"""Заполнение базы тестовыми данными из src/data/mock.js фронтенда.

    flask seed          # заполнить пустую базу
    flask seed --reset  # очистить все таблицы и заполнить заново

Пароль у всех тестовых пользователей: politech123 (вход под руководителем: ivan / politech123).
"""
import random
from datetime import datetime, time, timedelta

import click

from .extensions import db
from .models import (
    APP_TZ, BoardColumn, Chat, ChatMember, CompetencyTopic, Message, Project, ProjectStage, Recommendation, Report,
    Task, TaskComment, Technology, User, WorkLog, today,
)

PASSWORD = "politech123"

PEOPLE = [
    # login, имя, отдел, роль в команде, группа, роль доступа
    ("ivan", "Иван Иванов", "Аналитика", "Тим-лидер", "930-250", "leader"),
    ("roman", "Роман Романыч", "Бэкенд", "", "930-251", "student"),
    ("andrey", "Андрей Андреевич", "Дизайн", "", "930-250", "student"),
    ("elizaveta", "Елизавета Мельникова", "Аналитика", "", "930-252", "student"),
    ("alisa", "Алиса Устинова", "Фронтенд", "", "930-250", "student"),
    ("mark", "Марк Фёдорович", "Преподаватель", "", "", "leader"),
    ("artemiy", "Артемий Александрович", "Преподаватель", "", "", "leader"),
    ("olga", "Ольга Смирнова", "СММ", "", "930-251", "student"),
    ("dmitry", "Дмитрий Козлов", "Девопс", "", "930-253", "student"),
]

TECHS = [("python", "Python"), ("html", "HTML"), ("css", "CSS"), ("js", "JavaScript"), ("java", "Java"),
         ("php", "PHP"), ("csharp", "C#"), ("figma", "Дизайн"), ("excel", "Excel"), ("word", "Word")]

DESC = ("Составить план проекта и обсудить его с командой, добавить его в отчёт, доработать дизайн, "
        "прописать весь функционал каждой страницы и всех её составляющих.")
NOTES = ("Ускорить процесс работы, заранее распределять задачи и передавать их отделам, так же просить студентов "
         "отписываться, ставить реакции на сообщения с задачами.")
ALL_TAGS = ["Дизайн", "Python", "Программирование", "Статистика", "Отчёты", "Срочное", "Анализ"]

# колонка, название, прогресс, исполнитель (login), срок: дней от сегодня
TASKS = [
    ("progress", "Сверстать главную страницу", 70, "ivan", 3),
    ("progress", "Подключить авторизацию", 30, "roman", 1),
    ("progress", "Собрать отчёт за неделю", 45, "elizaveta", 2),
    ("plans", "Нарисовать экраны профиля", 15, "andrey", 6),
    ("plans", "Написать API для задач", 55, "roman", 10),
    ("plans", "Подготовить презентацию", 0, "alisa", 15),
    ("done", "Составить паспорт проекта", 100, "ivan", -8),
    ("done", "Распределить роли", 100, "elizaveta", -10),
    ("done", "Придумать тематику", 100, "andrey", -13),
]

PROJECT_TEXT = ("Создание приложения для управления студенческими проектами. Канбан-доска проекта: Визуализируйте "
                "весь путь проекта от стадии «Идея» до «Защита». Просто перетаскивайте задачи, чтобы отслеживать "
                "прогресс.")

STAGES = [("Разработать дизайн", 49), ("Создание паспорта", 12), ("Распределение ролей", 14),
          ("Разобрать статистику", 10), ("Придумать тематику", 5), ("Подготовить презентацию", 3),
          ("Провести тестирование", 2)]


def _at(days_ago: int, hh: int, mm: int) -> datetime:
    return datetime.combine(today() - timedelta(days=days_ago), time(hh, mm), tzinfo=APP_TZ)


def seed_all() -> None:
    rnd = random.Random(42)
    now = today()

    # --- справочники
    for tid, name in TECHS:
        db.session.add(Technology(id=tid, name=name))
    cols = {
        "progress": BoardColumn(key="progress", title="В процессе", color="#e63246", position=0),
        "plans": BoardColumn(key="plans", title="В планах", color="#b04bfe", position=1),
        "done": BoardColumn(key="done", title="Готовые", color="#4646f4", position=2, is_done=True),
    }
    db.session.add_all(cols.values())

    # --- пользователи
    users: dict[str, User] = {}
    for login, name, dept, team_role, group, role in PEOPLE:
        u = User(login=login, email=f"{login}@politech.test", name=name, full_name=name, department=dept,
                 team_role=team_role, group=group, role=role,
                 position="Преподаватель" if dept == "Преподаватель" else "Участник")
        u.set_password(PASSWORD)
        users[login] = u
        db.session.add(u)
    ivan = users["ivan"]
    ivan.full_name, ivan.email, ivan.phone = "Иван Иванов Иванович", "vania@mail.com", "+7 975 057 55 66"
    ivan.telegram, ivan.vk, ivan.sex = "@ivan_super", "Иван Иванов", "Мужской"
    ivan.birth = datetime(2007, 1, 1).date()
    ivan.faculty, ivan.course = "Транспортный факультет", 1
    ivan.direction = "01.03.02 Прикладная математика и информатика"
    db.session.flush()

    # --- проекты
    def project(title, leader, days_left, progress, status, members, start_ago, with_text=True, **kw):
        p = Project(title=title, leader_id=users[leader].id, progress=progress, status=status,
                    start=now - timedelta(days=start_ago),
                    end=now + timedelta(days=days_left) if status == "progress" else now - timedelta(days=140),
                    goal=PROJECT_TEXT, members=[users[m] for m in members], tasks=[], **kw)
        db.session.add(p)
        return p

    everyone = [p[0] for p in PEOPLE]
    students = [p[0] for p in PEOPLE if p[5] == "student" or p[0] == "ivan"]
    p1 = project("ProjectSprint", "ivan", 39, 30, "progress", everyone, 230,
                 relevance="Студенческие команды теряют задачи в чатах и таблицах — нужен единый инструмент.",
                 problem="Нет прозрачности: руководитель не видит, кто и что делает, и на каком этапе проект.")
    p1.stages = [ProjectStage(name=n, percent=v, position=i) for i, (n, v) in enumerate(STAGES)]
    project("ProjectsPrint", "elizaveta", 54, 30, "progress", ["elizaveta", "ivan", "roman", "olga"], 215)
    project("Умный кампус", "roman", 12, 64, "progress", ["roman", "dmitry", "alisa"], 200)
    project("ProjectSprint", "ivan", 0, 100, "done", students, 600)
    project("Транспорт 2.0", "andrey", 0, 100, "done", ["andrey", "alisa", "olga"], 600)
    db.session.flush()

    # --- задачи
    tasks = []
    for i, (col, title, progress, who, end_in) in enumerate(TASKS):
        end = now + timedelta(days=end_in)
        t = Task(column=cols[col], title=title, description=DESC, notes=NOTES, progress=progress,
                 assignee_id=users[who].id, author_id=ivan.id, project_id=p1.id, start=end - timedelta(days=30),
                 end=end, tags=list(ALL_TAGS), position=i,
                 created_at=_at(rnd.randint(5, 40), 10, 0))
        if col == "done":
            t.completed_at = datetime.combine(end, time(18, 0), tzinfo=APP_TZ)
        tasks.append(t)
        db.session.add(t)
    db.session.flush()

    for days_ago, who, text in [(20, "artemiy", "Проверь текст"), (19, "artemiy", "Не забудь сделать отчёт"),
                                (18, "artemiy", "Удали вводный знак"), (1, "mark", "Напиши побольше задач")]:
        db.session.add(TaskComment(task_id=tasks[0].id, author_id=users[who].id, text=text,
                                   created_at=_at(days_ago, 12, 0)))

    # --- учёт часов за последние ~140 дней
    workers = ["ivan", "roman", "andrey", "elizaveta", "alisa", "olga", "dmitry"]
    weight = {"ivan": 0.8, "roman": 0.65, "andrey": 0.5, "elizaveta": 0.45, "alisa": 0.4, "olga": 0.25,
              "dmitry": 0.3}
    for d in range(140):
        day = now - timedelta(days=d)
        for w in workers:
            if rnd.random() < weight[w] * (0.6 if day.weekday() >= 5 else 1):
                task = rnd.choice([t for t in tasks if t.assignee_id == users[w].id] or tasks)
                db.session.add(WorkLog(user_id=users[w].id, task_id=task.id, day=day,
                                       hours=round(rnd.uniform(1, 6) * 2) / 2))

    # --- компетенции
    def topics(login, tech, items):
        for title, status, notes in items:
            db.session.add(CompetencyTopic(user_id=users[login].id, tech_id=tech, title=title, status=status,
                                           notes=notes))

    topics("ivan", "python", [
        ("Введение в Python", "done", "Введение в язык Python предполагает последовательное освоение базовых "
                                      "конструкций. Переменная служит именованной областью для хранения данных "
                                      "определённого типа. Оператор присваивания фиксирует значение в памяти."),
        ("Числа и операторы", "done", "Арифметика, целые и вещественные числа, приоритет операций."),
        ("Строки и списки", "done", ""), ("Функции", "done", ""), ("Классы и объекты", "done", ""),
        ("Модули и пакеты", "done", ""), ("Исключения", "done", ""),
        ("Работа с API", "progress", "HTTP-запросы, библиотека requests, разбор JSON."),
    ])
    topics("ivan", "html", [("Семантическая вёрстка", "done", ""), ("Формы и валидация", "progress", "")])

    def generated(login, tech, percent, n=8):
        done = round(percent / 100 * n)
        topics(login, tech, [(f"Тема {i + 1}", "done" if i < done else "progress", "") for i in range(n)])

    for login, tech, pct in [("alisa", "python", 100), ("alisa", "js", 75), ("elizaveta", "python", 100),
                             ("elizaveta", "html", 50), ("roman", "python", 88), ("roman", "html", 50),
                             ("andrey", "figma", 88), ("andrey", "css", 63), ("dmitry", "python", 63),
                             ("dmitry", "js", 38), ("olga", "word", 75)]:
        generated(login, tech, pct)

    for days_ago, who, text, label, read in [
        (1, "mark", "Прочитай данную статью", "wwwpytot.ru", False),
        (14, "artemiy", "Ознакомься с файлом", "Основы Python", True),
        (22, "artemiy", "Посмотри лекцию про API", "Лекция 4", True),
    ]:
        db.session.add(Recommendation(author_id=users[who].id, recipient_id=ivan.id, text=text, link_label=label,
                                      link_href="#", is_read=read, created_at=_at(days_ago, 9, 0)))

    # --- отчёты
    for t, notes in [(tasks[0], "Ускорить процесс работы, заранее распределять задачи и передавать их отделам."),
                     (tasks[6], "Паспорт согласован с руководителем."),
                     (tasks[7], "Роли распределены, команда укомплектована.")]:
        db.session.add(Report(author_id=ivan.id, task_id=t.id, title=t.title, notes=notes,
                              created_at=_at(rnd.randint(1, 10), 15, 0)))

    # --- чаты
    def chat(title, members, is_group, msgs, unread=0, project_id=None):
        c = Chat(title=title if is_group else "", is_group=is_group, created_by=ivan.id, project_id=project_id,
                 created_at=msgs[0][1] - timedelta(days=1))
        c.members = [ChatMember(user_id=users[m].id) for m in dict.fromkeys(["ivan", *members])]
        db.session.add(c)
        db.session.flush()
        created = []
        for who, at, text in msgs:
            m = Message(chat_id=c.id, author_id=users[who].id, text=text, created_at=at)
            db.session.add(m)
            created.append(m)
        db.session.flush()
        for member in c.members:
            member.last_read_id = created[-1].id
        # непрочитанные для Ивана — последние `unread` сообщений
        mine = next(m for m in c.members if m.user_id == ivan.id)
        mine.last_read_id = created[-unread - 1].id if unread < len(created) else 0
        return c

    conv = [
        ("alisa", _at(0, 10, 10), "Привет! Я пропустил прошлую пару по Математике. Мог бы кто-нибудь скинуть фото "
                                  "конспекта? Что самое важное преподаватель говорил насчет курсача/контрольной?"),
        ("alisa", _at(0, 10, 11), "Можете пожалуйста предупредить преподавателя, что меня не будет на следующей паре!!"),
        ("alisa", _at(0, 10, 12), "Заранее большое спасибо)"),
        ("roman", _at(0, 10, 13), "Привет! Хорошо, приду домой и скину в личку"),
        ("alisa", _at(0, 10, 14), "Спасибо, жду!!!!!!"),
        ("roman", _at(0, 10, 15), "В течение получаса скину"),
        ("ivan", _at(0, 10, 15), "Привет! Я пропустил прошлую пару по Химии. Мог бы кто-нибудь скинуть фото "
                                 "конспекта? Что самое важное преподаватель говорил насчет курсача/контрольной?"),
        ("alisa", _at(0, 10, 16), "Привет! Я пропустил прошлую пару..."),
    ]
    p2 = db.session.scalar(db.select(Project).where(Project.title == "ProjectsPrint"))
    chat("ProjectsPrint", ["alisa", "roman", "elizaveta", "olga"], True, conv, unread=2, project_id=p2.id)
    chat("", ["roman"], False, [("ivan", _at(0, 10, 19), "Скинешь конспект?"),
                                ("roman", _at(0, 10, 21), "Хорошо, приду домой и скину в личку")], unread=1)
    chat("", ["elizaveta"], False, [("elizaveta", _at(0, 9, 47), "Отчёт загрузила в папку")])
    chat("Команда дизайна", ["andrey", "alisa", "olga", "elizaveta"], True,
         [("andrey", _at(0, 9, 5), "Начинаю экраны профиля"), ("alisa", _at(0, 9, 8), "Жду!"),
          ("andrey", _at(0, 9, 12), "Макеты профиля готовы")], unread=3)
    chat("", ["andrey"], False, [("andrey", _at(1, 18, 0), "Посмотри правки в Figma")])
    chat("", ["mark"], False, [("mark", _at(1, 16, 30), "Жду отчёт до пятницы")], unread=1)
    chat("", ["alisa"], False, [("ivan", _at(3, 12, 0), "Держи макеты"), ("alisa", _at(3, 12, 5), "Спасибо!")])
    chat("Бэкенд", ["roman", "dmitry", "alisa"], True, [("roman", _at(3, 11, 0), "Миграции накатил")])
    chat("", ["olga"], False, [("olga", _at(4, 14, 0), "Пост опубликован")])
    chat("", ["dmitry"], False, [("dmitry", _at(5, 20, 0), "Сервер перезапущен")])

    db.session.commit()


def reset_all() -> None:
    tables = ", ".join(f'"{t.name}"' for t in db.metadata.sorted_tables)
    db.session.execute(db.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db.session.commit()


def register_cli(app) -> None:
    @app.cli.command("seed")
    @click.option("--reset", is_flag=True, help="Очистить все таблицы перед заполнением")
    def seed_command(reset: bool):
        """Заполнить базу тестовыми данными."""
        if reset:
            reset_all()
        elif db.session.scalar(db.select(db.func.count(User.id))):
            raise click.ClickException("База уже заполнена. Используйте: flask seed --reset")
        seed_all()
        click.echo(f"Готово. Вход: ivan / {PASSWORD} (руководитель), alisa / {PASSWORD} (студент)")
