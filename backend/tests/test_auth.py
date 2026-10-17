"""Integration tests use a rollback transaction; existing data is preserved."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.security import password_hash, token_hash
from app.db.connection import get_db
from app.main import app

COOKIE_NAME = settings.cookie_name
DATABASE_URL = settings.database_url

HEADERS = {"X-Requested-With": "grading-web", "Origin": "http://localhost:5173"}
PASSWORD = "test-password-12345"


@pytest.fixture
def setup():
    db = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    uid = uuid4()
    email = f"auth-test-{uid}@example.com"
    db.execute("INSERT INTO users(id,email,display_name,password_hash) VALUES (%s,%s,%s,%s)",
               (uid, email, "Test Trainer", password_hash.hash(PASSWORD)))
    def test_connection():
        with db.transaction():
            yield db
    app.dependency_overrides[get_db] = test_connection
    try:
        with TestClient(app) as client:
            yield client, db, email, uid
    finally:
        app.dependency_overrides.clear()
        db.rollback()
        db.close()


def sign_in(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password}, headers=HEADERS)


def test_login_me_logout_revokes_copied_cookie(setup):
    client, db, email, _ = setup
    assert client.get("/api/auth/me").status_code == 401
    response = sign_in(client, email.upper())
    assert response.status_code == 200
    assert "password_hash" not in response.json()
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    token = client.cookies.get(COOKIE_NAME)
    assert db.execute("SELECT refresh_token_hash FROM auth_sessions WHERE refresh_token_hash=%s", (token_hash(token),)).fetchone()
    assert client.get("/api/auth/me").json()["email"] == email
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    client.cookies.set(COOKIE_NAME, token, path="/api/auth")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout", headers=HEADERS).status_code == 204


def test_bad_password_unknown_user_and_placeholder(setup):
    client, db, email, uid = setup
    assert sign_in(client, email, "wrong").status_code == 401
    assert sign_in(client, "missing@example.com").status_code == 401
    db.execute("UPDATE users SET password_hash='DEMO_ACCOUNT_NO_LOGIN' WHERE id=%s", (uid,))
    assert sign_in(client, email).status_code == 401


def test_expired_and_disabled_session(setup):
    client, db, email, uid = setup
    assert sign_in(client, email).status_code == 200
    db.execute("UPDATE auth_sessions SET expires_at=%s WHERE user_id=%s", (datetime.now(timezone.utc)-timedelta(seconds=1), uid))
    assert client.get("/api/auth/me").status_code == 401
    assert sign_in(client, email).status_code == 200
    db.execute("UPDATE users SET status='disabled' WHERE id=%s", (uid,))
    assert client.get("/api/auth/me").status_code == 401
    assert sign_in(client, email).status_code == 401


def test_login_rotates_session_and_csrf_protection(setup):
    client, _, email, _ = setup
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 403
    assert client.post("/api/auth/logout", headers={**HEADERS, "Origin": "https://other.example"}).status_code == 403
    assert sign_in(client, email).status_code == 200
    old = client.cookies.get(COOKIE_NAME)
    assert sign_in(client, email).status_code == 200
    assert client.cookies.get(COOKIE_NAME) != old
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, old, path="/api/auth")
    assert client.get("/api/auth/me").status_code == 401
