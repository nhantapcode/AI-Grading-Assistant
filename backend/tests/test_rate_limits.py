import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_login_limiter
from app.core.config import settings
from app.main import app
from app.repositories.rate_limits import RateLimitRepository
from app.services.rate_limits import LoginRateLimiter
from test_auth import HEADERS, setup


@pytest.fixture
def repository():
    class TrackedRepository(RateLimitRepository):
        keys: set[str]

        def __init__(self):
            super().__init__(settings.database_url)
            self.keys = set()

        def consume(self, limits, window_seconds):
            self.keys.update(key for key,_ in limits)
            return super().consume(limits,window_seconds)

    repo = TrackedRepository()
    yield repo
    with psycopg.connect(settings.database_url) as db:
        db.execute('DELETE FROM auth_rate_limits WHERE key_hash=ANY(%s)',(list(repo.keys),))


def test_ip_limit_blocks_before_password_verification(setup,repository,monkeypatch):
    from app.services import auth
    calls = []
    original = auth.verify_password
    def verify(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(auth,'verify_password',verify)
    limiter = LoginRateLimiter(repository,2,10,60)
    app.dependency_overrides[get_login_limiter] = lambda: limiter
    address = f'test-ip-{uuid4()}'
    with TestClient(app,client=(address,50000)) as client:
        for _ in range(2):
            assert client.post('/api/auth/login',headers=HEADERS,json={'email':f'{uuid4()}@example.test','password':'wrong'}).status_code==401
        blocked = client.post('/api/auth/login',headers={**HEADERS,'X-Forwarded-For':'different-ip'},json={'email':f'{uuid4()}@example.test','password':'wrong'})
    assert blocked.status_code==429
    assert 1<=int(blocked.headers['retry-after'])<=60
    assert blocked.headers['cache-control']=='no-store'
    assert len(calls)==2


def test_account_limit_normalizes_email_across_clients(setup,repository):
    limiter = LoginRateLimiter(repository,10,2,60)
    app.dependency_overrides[get_login_limiter] = lambda: limiter
    email = f'limit-{uuid4()}@example.test'
    for index in range(3):
        with TestClient(app,client=(f'account-ip-{uuid4()}',50000)) as client:
            result = client.post('/api/auth/login',headers=HEADERS,json={'email':f' {email.upper()} ' if index==2 else email,'password':'wrong'})
        assert result.status_code==(429 if index==2 else 401)


def test_shared_counter_is_atomic_and_expires(repository):
    key = hashlib.sha256(str(uuid4()).encode()).hexdigest()
    barrier = Barrier(6)
    def consume(_):
        barrier.wait(timeout=10)
        return repository.consume([(key,2)],60)
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(consume,range(6)))
    assert results.count(0)==2
    assert len([result for result in results if result>0])==4
    with psycopg.connect(settings.database_url) as db:
        db.execute("UPDATE auth_rate_limits SET expires_at=clock_timestamp()-interval '1 second' WHERE key_hash=%s",(key,))
    assert RateLimitRepository(settings.database_url).consume([(key,2)],60)==0


def test_limiter_failure_does_not_allow_login(setup):
    class Unavailable:
        def check(self,address,email):
            raise psycopg.OperationalError('database unavailable')
    app.dependency_overrides[get_login_limiter] = lambda: Unavailable()
    client,_,email,_ = setup
    response = client.post('/api/auth/login',headers=HEADERS,json={'email':email,'password':'wrong'})
    assert response.status_code==503
    assert response.headers['retry-after']=='5'
