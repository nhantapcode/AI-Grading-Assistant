import hashlib

from app.repositories.rate_limits import RateLimitRepository


class LoginRateLimiter:
    def __init__(self, repository: RateLimitRepository, ip_limit: int, account_limit: int, window_seconds: int) -> None:
        if min(ip_limit,account_limit,window_seconds)<1:
            raise ValueError('Login limits and window must be positive')
        self.repository = repository
        self.ip_limit = ip_limit
        self.account_limit = account_limit
        self.window_seconds = window_seconds

    def check(self, address: str, email: str) -> int:
        keys = [('login:ip:'+address,self.ip_limit),('login:account:'+email.strip().lower(),self.account_limit)]
        limits = [(hashlib.sha256(key.encode()).hexdigest(),limit) for key,limit in keys]
        return self.repository.consume(limits,self.window_seconds)
