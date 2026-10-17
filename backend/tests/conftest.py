import pytest

from app.api.dependencies import get_login_limiter
from app.main import app


class NoLoginLimit:
    def check(self, address: str, email: str) -> int:
        return 0


@pytest.fixture(autouse=True)
def isolate_login_counters():
    # Non-rate-limit tests must not consume real user/IP quotas.
    app.dependency_overrides[get_login_limiter] = lambda: NoLoginLimit()
    yield
    app.dependency_overrides.pop(get_login_limiter,None)
