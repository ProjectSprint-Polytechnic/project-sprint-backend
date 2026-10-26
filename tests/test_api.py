import io


# ------------------------------------------------------------------ авторизация

def test_register_validation_matches_frontend(client):
    r = client.post("/api/auth/register", json={"login": "ab", "password": "123", "password2": "1234"})
    assert r.status_code == 422
    assert set(r.json["fields"]) == {"login", "pass2"} or "login" in r.json["fields"]
    r = client.post("/api/auth/register", json={"login": "newbie", "password": "secret1", "password2": "secret2"})
    assert r.json["fields"] == {"pass2": "Пароли не совпадают"}


def test_register_login_refresh_logout(client):
    r = client.post("/api/auth/register", json={"login": "newbie", "password": "secret1", "password2": "secret1"})
    assert r.status_code == 201
    assert r.json["user"]["accountRole"] == "student"
    assert client.post("/api/auth/register", json={"login": "NEWBIE", "password": "secret1"}).status_code == 422

    assert client.post("/api/auth/login", json={"login": "newbie", "password": "wrong!"}).status_code == 401
    r = client.post("/api/auth/login", json={"login": "newbie", "password": "secret1"})
    access, refresh = r.json["accessToken"], r.json["refreshToken"]

    r = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 200 and r.json["accessToken"]

    h = {"Authorization": f"Bearer {access}"}
    assert client.get("/api/me", headers=h).status_code == 200
    assert client.post("/api/auth/logout", headers=h, json={"refreshToken": refresh}).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401


def test_login_by_email_and_auth_required(client):
    assert client.post("/api/auth/login", json={"login": "vania@mail.com", "password": "politech123"}).status_code == 200
    r = client.get("/api/tasks")
    assert r.status_code == 401 and r.json["error"] == "Требуется авторизация"


# ------------------------------------------------------------------ профиль

def test_profile_and_settings(client, student):
    r = client.patch("/api/me", headers=student, json={"telegram": "@alisa", "course": 2, "birth": "01.02.2006"})
    assert r.status_code == 200
    assert r.json["telegram"] == "@alisa" and r.json["course"] == 2 and r.json["birth"] == "2006-02-01"
    r = client.patch("/api/me/settings", headers=student, json={"theme": "dark", "notify": {"all": True}})
    assert r.json["theme"] == "dark" and all(r.json["notify"].values())
    r = client.post("/api/me/password", headers=student, json={"oldPassword": "politech123", "newPassword": "newpass1"})
    assert r.status_code == 200
    assert client.post("/api/auth/login", json={"login": "alisa", "password": "newpass1"}).status_code == 200


# ------------------------------------------------------------------ задачи

def test_task_lifecycle(client, student, leader):
    r = client.post("/api/tasks", headers=student, json={
        "column": "plans", "title": "Написать тесты", "tags": ["Python"], "start": "2026-10-01", "end": "2026-10-30"})
    assert r.status_code == 201
    task = r.json
    assert task["assignee"] == 5 and task["progress"] == 0 and task["columnKey"] == "plans"

    r = client.patch(f"/api/tasks/{task['id']}", headers=student, json={"progress": 40})
    assert r.json["progress"] == 40
    r = client.patch(f"/api/tasks/{task['id']}", headers=student, json={"column": "done"})
    assert r.json["progress"] == 100 and r.json["completedAt"]

    assert client.patch(f"/api/tasks/{task['id']}", headers=student, json={"end": "2026-09-01"}).status_code == 422
    assert client.get("/api/tasks?q=тесты", headers=student).json[0]["id"] == task["id"]
    assert client.delete(f"/api/tasks/{task['id']}", headers=student).status_code == 204


def test_task_permissions(client, student, leader):
    # задача 2 принадлежит Роману — Алиса не может её менять/удалять, руководитель может
    assert client.patch("/api/tasks/2", headers=student, json={"progress": 99}).status_code == 403
    assert client.delete("/api/tasks/2", headers=student).status_code == 403
    assert client.delete("/api/tasks/2", headers=leader).status_code == 204


def test_columns_leader_only(client, student, leader):
    assert client.post("/api/columns", headers=student, json={"title": "Тест", "color": "#ff0000"}).status_code == 403
    r = client.post("/api/columns", headers=leader,
                    json={"title": "Ревью", "color": "#039be5", "task": {"title": "Проверить PR"}})
    assert r.status_code == 201 and r.json["task"]["column"] == r.json["id"]
    assert client.delete(f"/api/columns/{r.json['id']}", headers=leader).status_code == 422  # есть задачи
    assert client.delete(f"/api/columns/{r.json['id']}?moveTo=2", headers=leader).status_code == 204
    assert client.post("/api/columns", headers=leader, json={"title": "X", "color": "red"}).status_code == 422


def test_comments_and_deadlines(client, student):
    r = client.post("/api/tasks/1/comments", headers=student, json={"text": "Готово к ревью"})
    assert r.status_code == 201 and r.json["mine"]
    comments = client.get("/api/tasks/1/comments", headers=student).json
    assert comments[0]["text"] == "Готово к ревью"
    assert client.get("/api/tasks/1", headers=student).json["comments"] == 5

    d = client.get("/api/deadlines", headers=student).json
    assert set(d) == {"overdue", "week", "later"}
    assert all(t["columnKey"] != "done" for g in d.values() for t in g)
    assert len(d["week"]) == 4 and len(d["later"]) == 2


# ------------------------------------------------------------------ компетенции

def test_competencies(client, student, leader):
    r = client.post("/api/competencies/topics", headers=student, json={"tech": "java", "title": "ООП"})
    assert r.status_code == 201
    java = next(c for c in client.get("/api/competencies", headers=student).json if c["tech"] == "java")
    assert java["percent"] == 0
    client.patch(f"/api/competencies/topics/{r.json['id']}", headers=student, json={"status": "done"})
    java = next(c for c in client.get("/api/competencies", headers=student).json if c["tech"] == "java")
    assert java["percent"] == 100
    assert client.post("/api/competencies/topics", headers=student, json={"tech": "cobol", "title": "x"}).status_code == 422

    assert client.get("/api/competencies/team", headers=student).status_code == 403
    team = client.get("/api/competencies/team", headers=leader).json
    assert any(m["person"] == 5 and ["java", 100] in m["skills"] for m in team)


def test_recommendations(client, student, leader):
    assert client.post("/api/recommendations", headers=student, json={"to": 1, "text": "x"}).status_code == 403
    r = client.post("/api/recommendations", headers=leader,
                    json={"to": 5, "text": "Прочитай про декораторы", "link": {"label": "Статья", "href": "https://x"}})
    assert r.status_code == 201
    mine = client.get("/api/recommendations", headers=student).json
    assert mine[0]["isNew"] and mine[0]["link"]["label"] == "Статья"
    assert client.post(f"/api/recommendations/{mine[0]['id']}/read", headers=student).json["isNew"] is False


# ------------------------------------------------------------------ проекты

def test_projects(client, student, leader):
    assert client.post("/api/projects", headers=student, json={"title": "X"}).status_code == 403
    assert client.post("/api/projects", headers=leader, json={"title": " "}).status_code == 422
    r = client.post("/api/projects", headers=leader, json={
        "title": "Новый проект", "goal": "Цель", "tasks": ["Сделать MVP"], "members": [2, 3], "leader": 4,
        "start": "2026-10-01", "end": "2026-12-31", "stages": [{"name": "Дизайн", "percent": 20}]})
    assert r.status_code == 201
    p = r.json
    assert p["members"] == 3 and p["memberIds"] == [2, 3, 4] and p["stages"][0]["name"] == "Дизайн"
    assert p["daysLeft"] > 0
    r = client.patch(f"/api/projects/{p['id']}", headers=leader, json={"status": "done"})
    assert r.json["progress"] == 100 and r.json["daysLeft"] == 0
    progress = client.get("/api/projects?status=progress", headers=student).json
    assert all(x["status"] == "progress" for x in progress)


# ------------------------------------------------------------------ отчёты и файлы

def test_reports_with_files(client, student, app):
    r = client.post("/api/files", headers=student,
                    data={"file": (io.BytesIO(b"hello report"), "Отчёт неделя 1.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 201
    fid = r.json["id"]
    assert r.json["name"] == "Отчёт неделя 1.pdf"

    r = client.post("/api/reports", headers=student, json={"taskId": 7, "notes": "Сделано", "files": [fid]})
    assert r.status_code == 201
    report = r.json
    assert report["title"] == "Составить паспорт проекта" and report["files"][0]["id"] == fid

    r = client.get(f"/api/files/{fid}", headers=student)
    assert r.status_code == 200 and r.data == b"hello report"
    # файл нельзя прикрепить второй раз к другому объекту
    assert client.post("/api/reports", headers=student, json={"taskId": 8, "files": [fid]}).status_code == 422

    assert client.delete(f"/api/reports/{report['id']}", headers=student).status_code == 204
    assert client.get(f"/api/files/{fid}", headers=student).status_code == 404

    bad = client.post("/api/files", headers=student, data={"file": (io.BytesIO(b"x"), "virus.exe")},
                      content_type="multipart/form-data")
    assert bad.status_code == 422


# ------------------------------------------------------------------ чаты

def test_chats(client, student, login):
    r = client.post("/api/chats", headers=student, json={"person": 9})
    assert r.status_code == 201 and r.json["title"] == "Дмитрий Козлов"
    chat_id = r.json["id"]
    again = client.post("/api/chats", headers=student, json={"person": 9})
    assert again.status_code == 200 and again.json["id"] == chat_id

    assert client.post(f"/api/chats/{chat_id}/messages", headers=student, json={"text": ""}).status_code == 422
    msg = client.post(f"/api/chats/{chat_id}/messages", headers=student, json={"text": "Привет!"}).json
    assert msg["mine"] and msg["time"]

    dmitry = login("dmitry")
    chat = next(c for c in client.get("/api/chats", headers=dmitry).json if c["id"] == chat_id)
    assert chat["unread"] == 1 and chat["last"] == "Привет!" and chat["title"] == "Алиса Устинова"
    assert client.get(f"/api/chats/{chat_id}/messages?after={msg['id']}", headers=dmitry).json == []
    assert len(client.get(f"/api/chats/{chat_id}/messages", headers=dmitry).json) == 1
    chat = next(c for c in client.get("/api/chats", headers=dmitry).json if c["id"] == chat_id)
    assert chat["unread"] == 0

    # чужой чат недоступен
    olga = login("olga")
    assert client.get(f"/api/chats/{chat_id}/messages", headers=olga).status_code == 404

    g = client.post("/api/chats", headers=student, json={"title": "Фронт", "isGroup": True, "members": [2, 3]})
    assert g.status_code == 201 and g.json["members"] == 3 and g.json["isGroup"]


def test_seeded_unread(client, leader):
    chats = client.get("/api/chats", headers=leader).json
    assert len(chats) == 10
    assert client.get("/api/chats/unread", headers=leader).json["unread"] == sum(c["unread"] for c in chats) > 0


# ------------------------------------------------------------------ статистика и помощь

def test_stats_and_worklogs(client, student, leader):
    before = client.get("/api/stats?period=week", headers=leader).json
    assert client.post("/api/worklogs", headers=student, json={"hours": 30}).status_code == 422
    assert client.post("/api/worklogs", headers=student, json={"hours": 4.5, "taskId": 6}).status_code == 201
    after = client.get("/api/stats?period=week", headers=leader).json
    assert round(after["hours"] - before["hours"]) in (4, 5)
    assert len(after["activity"]) == 7 and len(after["activityLabels"]) == 7
    assert {d["label"] for d in after["distribution"]} == {"В процессе", "В планах", "Готовые"}
    assert after["team"][0]["crown"] == "red"
    assert len(client.get("/api/stats", headers=leader).json["activity"]) == 20
    assert client.get("/api/stats?period=year", headers=leader).status_code == 422
    assert client.get("/api/worklogs?user=1", headers=student).status_code == 403


def test_help(client, student, leader):
    assert client.post("/api/help", headers=student, json={"text": ""}).status_code == 422
    assert client.post("/api/help", headers=student, json={"text": "Не грузится аватар"}).status_code == 201
    assert len(client.get("/api/help", headers=leader).json) == 1
