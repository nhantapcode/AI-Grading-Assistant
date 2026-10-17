from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from app.core.security import password_hash, token_hash
from app.core.config import settings
from app.main import app
from test_auth import HEADERS, PASSWORD, setup, sign_in


def organization(db, user_id, role="owner"):
    org = db.execute("INSERT INTO organizations(name) VALUES ('Invitation Test') RETURNING id").fetchone()["id"]
    db.execute("INSERT INTO memberships(organization_id,user_id,role) VALUES (%s,%s,%s)", (org,user_id,role))
    return org


def invite(client, org, email, role="trainer"):
    return client.post(f"/api/organizations/{org}/invitations", json={"email":email,"role":role}, headers=HEADERS)


def post(client, path, body=None):
    return client.post(f"/api/{path}", json=body, headers=HEADERS)


def test_new_account_flow_and_replay(setup):
    client, db, email, uid = setup
    org = organization(db, uid)
    assert sign_in(client,email).status_code == 200
    response = invite(client,org,"NEW@example.com")
    assert response.status_code == 201
    data = response.json()
    token = data["link"].split("#invite=")[1]
    row = db.execute("SELECT token_hash FROM account_invitations WHERE id=%s", (data["id"],)).fetchone()
    assert row["token_hash"] == token_hash(token)
    assert "token_hash" not in data
    assert client.get(f"/api/organizations/{org}/members").status_code == 200
    assert post(client,"auth/logout").status_code == 204
    assert post(client,"invitations/resolve", {"token":token}).json()["account_exists"] is False
    body = {"token":token,"display_name":"New Trainer","password":PASSWORD}
    assert post(client,"invitations/accept",body).status_code == 200
    assert post(client,"invitations/accept",body).status_code == 410
    assert sign_in(client,"new@example.com").status_code == 200
    organizations = client.get("/api/organizations").json()
    assert organizations[0]["role"] == "trainer"
    user = db.execute("SELECT password_hash FROM users WHERE email='new@example.com'").fetchone()
    assert user["password_hash"] != PASSWORD
    assert password_hash.verify(PASSWORD,user["password_hash"])
    assert invite(client,org,"another@example.com").status_code == 403


def test_permissions_and_tenant_isolation(setup):
    client, db, email, uid = setup
    org = organization(db,uid,"admin")
    other = db.execute("INSERT INTO organizations(name) VALUES ('Other') RETURNING id").fetchone()["id"]
    sign_in(client,email)
    assert invite(client,org,"trainer@example.com").status_code == 201
    assert invite(client,org,"admin@example.com","admin").status_code == 403
    assert invite(client,other,"trainer@example.com").status_code == 403
    assert client.get(f"/api/organizations/{other}/invitations").status_code == 403
    assert client.get(f"/api/organizations/{other}/members").status_code == 403
    db.execute("UPDATE memberships SET status='revoked' WHERE user_id=%s", (uid,))
    assert invite(client,org,"trainer@example.com").status_code == 403


def test_revocation_expiry_invalid_token_and_revoked_inviter(setup):
    client, db, email, uid = setup
    org = organization(db,uid)
    sign_in(client,email)
    for state in ("revoked","expired","inviter_revoked"):
        result = invite(client,org,f"{state}@example.com").json()
        token = result["link"].split("#invite=")[1]
        if state == "revoked":
            assert post(client,f"organizations/{org}/invitations/{result['id']}/revoke").status_code == 204
        elif state == "expired":
            db.execute("UPDATE account_invitations SET created_at=now()-interval '3 days', expires_at=now()-interval '1 day' WHERE id=%s", (result["id"],))
        else:
            db.execute("UPDATE memberships SET status='revoked' WHERE user_id=%s", (uid,))
        expected = 403 if state == "inviter_revoked" else 410
        assert post(client,"invitations/resolve", {"token":token}).status_code == expected
        assert post(client,"invitations/accept", {"token":token,"display_name":"Test","password":PASSWORD}).status_code == expected
    assert post(client,"invitations/resolve", {"token":"x"*43}).status_code == 404


def test_existing_user_must_authenticate_correct_email(setup):
    client, db, email, uid = setup
    org = organization(db,uid)
    existing_email = f"existing-{uuid4()}@example.com"
    db.execute("INSERT INTO users(email,display_name,password_hash) VALUES (%s,'Existing',%s)", (existing_email,password_hash.hash(PASSWORD)))
    sign_in(client,email)
    result = invite(client,org,existing_email).json()
    token = result["link"].split("#invite=")[1]
    assert post(client,"invitations/resolve", {"token":token}).json()["account_exists"] is True
    assert post(client,"invitations/accept", {"token":token}).status_code == 403
    post(client,"auth/logout")
    assert post(client,"invitations/accept", {"token":token}).status_code == 401
    assert sign_in(client,existing_email).status_code == 200
    assert post(client,"invitations/accept", {"token":token}).status_code == 200
    assert db.execute("SELECT count(*) AS n FROM users WHERE email=%s", (existing_email,)).fetchone()["n"] == 1


def test_validation_and_missing_csrf_header(setup):
    client, db, email, uid = setup
    org = organization(db,uid)
    sign_in(client,email)
    assert invite(client,org,"invalid").status_code == 422
    assert invite(client,org,"valid@example.com","owner").status_code == 422
    response = client.post(f"/api/organizations/{org}/invitations", json={"email":"a@example.com","role":"trainer"})
    assert response.status_code == 403


def test_concurrent_accept_only_creates_one_membership():
    # Independent committed connections exercise PostgreSQL row locking.
    owner_id, org_id = uuid4(), uuid4()
    token = str(uuid4()) + str(uuid4())
    email = f"race-{uuid4()}@example.com"
    owner_email = f"race-owner-{owner_id}@example.com"
    try:
        with psycopg.connect(settings.database_url) as db:
            db.execute("INSERT INTO users(id,email,display_name,password_hash) VALUES (%s,%s,'Race Owner',%s)", (owner_id,owner_email,password_hash.hash(PASSWORD)))
            db.execute("INSERT INTO organizations(id,name) VALUES (%s,'Race Test')", (org_id,))
            db.execute("INSERT INTO memberships(organization_id,user_id,role) VALUES (%s,%s,'owner')", (org_id,owner_id))
            db.execute("""INSERT INTO account_invitations(organization_id,email,role,token_hash,invited_by,expires_at)
                VALUES (%s,%s,'trainer',%s,%s,now()+interval '48 hours')""", (org_id,email,token_hash(token),owner_id))
        barrier = Barrier(2)

        def accept():
            with TestClient(app) as client:
                barrier.wait(timeout=10)
                return post(client,"invitations/accept", {"token":token,"display_name":"Race Trainer","password":PASSWORD}).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: accept(), range(2)))
        assert sorted(results) == [200,410]
        with psycopg.connect(settings.database_url, row_factory=dict_row) as db:
            assert db.execute("SELECT count(*) AS n FROM memberships WHERE organization_id=%s", (org_id,)).fetchone()["n"] == 2
    finally:
        # Only records owned by this test are removed.
        with psycopg.connect(settings.database_url) as db:
            db.execute("DELETE FROM account_invitations WHERE organization_id=%s", (org_id,))
            db.execute("DELETE FROM memberships WHERE organization_id=%s", (org_id,))
            db.execute("DELETE FROM organizations WHERE id=%s", (org_id,))
            db.execute("DELETE FROM users WHERE email IN (%s,%s)", (email,owner_email))
