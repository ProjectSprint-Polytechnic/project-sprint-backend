# ProjectSprint Mobile Backend

Бэкенд ProjectSprint Mobile. Мобильный трекер командных проектов для студентов.

REST API для [веб-интерфейса ProjectSprint Mobile](https://github.com/ProjectSprint-Polytechnic/ProjectNew): вход и регистрация, канбан задач, дедлайны, компетенции и рекомендации, проекты, отчёты с файлами, чаты, статистика, профиль, настройки и «Помощь».

## Быстрый старт через Docker

```bash
docker compose up --build
```

- API: http://localhost:5001/api
- Проверка: http://localhost:5001/api/health → `{"status": "ok"}`
- Миграции применяются автоматически, база сразу заполняется тестовыми данными (`SEED=1` в `docker-compose.yml`).

## Запуск без Docker

Нужны Python 3.11+ и PostgreSQL 14+.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# создайте пользователя и базы в PostgreSQL
psql -U postgres -c "CREATE USER politech WITH PASSWORD 'politech';"
psql -U postgres -c "CREATE DATABASE politech OWNER politech;"
psql -U postgres -c "CREATE DATABASE politech_test OWNER politech;"

cp .env.example .env               # при необходимости поправьте DATABASE_URL
flask db upgrade                   # создать таблицы
flask seed                         # тестовые данные (flask seed --reset — заново)
flask run --port 5000 --debug      # http://localhost:5000
```

Тесты (16 тестов на отдельной базе `politech_test`):

```bash
pytest -q
```

Продакшен: `gunicorn -w 3 -b 0.0.0.0:5000 wsgi:app`. Обязательно задайте свои `SECRET_KEY` и `JWT_SECRET_KEY`.

## Коллекция Insomnia

Импортируйте [politech-insomnia.json](docs/politech-insomnia.json) в Insomnia. Коллекция содержит запросы к API и переменные окружения для локального запуска.

## Тестовые пользователи

Пароль у всех — `politech123`.

| Логин | Кто | Роль |
|---|---|---|
| `ivan` | Иван Иванов, тим-лидер | руководитель |
| `mark`, `artemiy` | преподаватели | руководитель |
| `alisa`, `roman`, `andrey`, `elizaveta`, `olga`, `dmitry` | студенты | студент |

Войти можно по логину или по email (`vania@mail.com`).

## Авторизация

JWT-токены. После `POST /api/auth/login` в ответе приходят `accessToken`, `refreshToken` и `user`. Во все остальные запросы передавайте заголовок:

```
Authorization: Bearer <accessToken>
```

Access-токен живёт 12 часов, refresh — 30 дней (`POST /api/auth/refresh` с refresh-токеном в заголовке).

Роль хранится в базе (`accountRole`: `student` | `leader`), а не переключается в браузере. Только руководителю доступны:
- создание разделов (колонок);
- создание и удаление проектов;
- рекомендации студентам;
- навыки команды;
- смена ролей.

## Эндпоинты

Все адреса начинаются с `/api`. Ошибки возвращаются в виде `{"error": "текст", "fields": {"поле": "текст"}}` с кодом 4xx. Для ошибок валидации это код 422, а ключи в `fields` совпадают с ключами `errors` во фронтенде (`login`, `pass`, `pass2`).

| Раздел фронта | Метод и адрес | Что делает |
|---|---|---|
| Вход | `POST /auth/register` | `{login, password, password2, name?, email?}` |
| | `POST /auth/login` | `{login, password, remember?}` |
| | `POST /auth/refresh`, `POST /auth/logout`, `POST /auth/restore` | обновить токен / выйти / «Восстановить» |
| Профиль, Настройки | `GET/PATCH /me` | данные профиля (объект `me`) |
| | `PATCH /me/settings` | `{theme, lang, notify}` |
| | `POST /me/password` | `{oldPassword, newPassword}` |
| Люди | `GET /users?q=`, `GET /users/:id` | массив `people` |
| | `PATCH /users/:id/role` | сменить роль (руководитель) |
| Справочники | `GET /meta` | хештеги, цвета разделов, технологии |
| Задачи | `GET /columns`, `POST/PATCH/DELETE /columns/:id` | разделы доски |
| | `GET /tasks?q=&column=&assignee=me&done=` | список задач |
| | `POST /tasks`, `GET/PATCH/DELETE /tasks/:id` | работа с задачей |
| | `PATCH /tasks/:id {column}` | перетаскивание; в «Готовые» ставит 100% |
| | `GET/POST /tasks/:id/comments`, `DELETE /comments/:id` | комментарии |
| Дедлайны | `GET /deadlines?mine=1` | `{overdue, week, later}` |
| Часы | `GET/POST /worklogs`, `DELETE /worklogs/:id` | учёт часов `{hours, date?, taskId?}` |
| Компетенции | `GET /competencies?user=` | формат `myCompetencies`, процент = доля тем со статусом done |
| | `POST/PATCH/DELETE /competencies/topics/:id` | «Добавить компетенцию», редактировать тему |
| | `GET /competencies/team`, `GET /competencies/departments` | для руководителя |
| | `GET/POST /recommendations`, `POST /recommendations/:id/read`, `POST /recommendations/read-all` | рекомендации |
| Проекты | `GET /projects?status=&mine=1&q=`, `POST`, `GET/PATCH/DELETE /projects/:id` | вместе с этапами `stages` и участниками `members` (id) |
| Отчёты | `GET /reports?all=1`, `POST /reports {taskId, notes, files}`, `GET/PATCH/DELETE /reports/:id` | отчёты по задачам |
| Сообщения | `GET /chats?q=`, `POST /chats` | создать чат: `{person}` — личный (без дублей), `{title, isGroup, members}` — групповой, `{projectId}` — чат проекта |
| | `GET /chats/:id/messages?after=&before=&q=` | переписка; открытие отмечает сообщения прочитанными |
| | `POST /chats/:id/messages {text, files}` | отправить сообщение |
| | `POST /chats/:id/read`, `GET /chats/unread`, `PATCH /chats/:id`, `POST /chats/:id/leave` | прочтение, счётчик, участники, выход |
| Статистика | `GET /stats?period=all\|month\|week&q=` | KPI, `distribution`, `workHours`, `activity`, `team` по реальным данным |
| Файлы | `POST /files` (multipart, поле `file` или `files`) | загрузка → `{id, name, url}` |
| | `GET /files/:id?inline=1`, `DELETE /files/:id` | скачать или удалить |
| Помощь | `POST /help {text, files}`, `GET /help`, `PATCH /help/:id` | обращения в поддержку |

### Как прикреплять файлы

1. Загрузите файл: `POST /api/files` как `multipart/form-data`. В ответе придёт `{"id": 12, "name": "Отчёт.pdf", "url": "/api/files/12"}`.
2. Передайте id при создании: `POST /api/reports {"taskId": 7, "notes": "...", "files": [12]}`. Так же работает для задач, тем компетенций, сообщений, рекомендаций и «Помощи».
3. Аватар: `PATCH /api/me {"avatarId": 12}`.

## Подключение фронтенда

Инструкции для совместного запуска находятся в [репозитории фронтенда](https://github.com/ProjectSprint-Polytechnic/ProjectNew#readme). Разместите оба репозитория рядом: `project-sprint-backend` и `ProjectNew`.

Фронтенд обращается к `/api` (переменная `VITE_API_BASE_URL`). При разработке Vite перенаправляет эти запросы на `http://localhost:5001` (переменная `API_PROXY_TARGET`), а при совместном запуске через Docker это делает nginx. Для запуска Flask напрямую на порту 5000 задайте `API_PROXY_TARGET=http://localhost:5000`. При обращении браузера к другому origin добавьте адрес фронтенда в `CORS_ORIGINS`.

При работе с ответами API учитывайте:

- `task.column` содержит числовой id колонки, `task.columnKey` содержит ключ базового раздела (`progress`, `plans`, `done`). При создании задачи `column` принимает id или ключ.
- Даты приходят в формате ISO (`2026-10-21`).
- `docs` и `files` содержат объекты `{id, name, url}`. Для скачивания файлов нужен заголовок `Authorization`.
- У сообщений `mine` показывает, что сообщение отправил текущий пользователь, а `from` содержит id автора.
- Роль пользователя приходит в `user.accountRole` (`student` или `leader`).
- Новые сообщения доступны через `GET /api/chats/:id/messages?after=<последний id>`.

## Структура

```
app/
  __init__.py      create_app(), обработчики ошибок, JWT
  config.py        настройки (из переменных окружения / .env)
  models.py        таблицы PostgreSQL (SQLAlchemy 2)
  utils.py         проверка полей, права, текущий пользователь
  seed.py          тестовые данные из mock.js (команда flask seed)
  api/             эндпоинты по разделам: auth, users, tasks, competencies,
                   projects, reports, chats, stats, files, meta
migrations/        миграции Alembic (flask db upgrade)
tests/             pytest
```

## Чего пока нет

- **Почта:** «Восстановить пароль» принимает заявку, но писем не отправляет — нужен SMTP-сервер.
- **WebSocket:** чат работает через опрос. Если нужно мгновенно, можно добавить Flask-SocketIO.
- **Несколько досок:** доска задач одна на всех. Задачу можно привязать к проекту через `projectId` и фильтровать `?projectId=`.
