"""Тесты гоняются на отдельной PostgreSQL-базе (TEST_DATABASE_URL). Перед каждым тестом — чистые тестовые данные."""
import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.seed import PASSWORD, reset_all, seed_all


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    class Cfg(TestConfig):
        UPLOAD_FOLDER = str(tmp_path_factory.mktemp("uploads"))

    app = create_app(Cfg)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    with app.app_context():
        reset_all()
        seed_all()
        db.session.remove()
    return app.test_client()


def _login(client, login):
    r = client.post("/api/auth/login", json={"login": login, "password": PASSWORD})
    assert r.status_code == 200, r.json
    return {"Authorization": f"Bearer {r.json['accessToken']}"}


@pytest.fixture()
def leader(client):
    """ivan — руководитель (id=1)"""
    return _login(client, "ivan")


@pytest.fixture()
def student(client):
    """alisa — студент (id=5)"""
    return _login(client, "alisa")


@pytest.fixture()
def login(client):
    return lambda name: _login(client, name)
