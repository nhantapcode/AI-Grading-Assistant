import psycopg
from psycopg.rows import dict_row


class RateLimitRepository:
    """Failed login transactions must not roll back rate-limit counters."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def consume(self, limits: list[tuple[str,int]], window_seconds: int) -> int:
        retry_after = 0
        with psycopg.connect(self.database_url,row_factory=dict_row) as db:
            db.execute('DELETE FROM auth_rate_limits WHERE expires_at<=clock_timestamp()')
            # Scope order is always IP then account, across all API workers.
            for key,limit in limits:
                row = db.execute("""INSERT INTO auth_rate_limits(key_hash,request_count,expires_at)
                    VALUES (%s,1,clock_timestamp()+make_interval(secs=>%s))
                    ON CONFLICT (key_hash) DO UPDATE SET
                      request_count=CASE WHEN auth_rate_limits.expires_at<=clock_timestamp() THEN 1 ELSE least(auth_rate_limits.request_count,%s)+1 END,
                      expires_at=CASE WHEN auth_rate_limits.expires_at<=clock_timestamp() THEN clock_timestamp()+make_interval(secs=>%s) ELSE auth_rate_limits.expires_at END
                    RETURNING request_count,greatest(1,ceil(extract(epoch FROM (expires_at-clock_timestamp()))))::integer AS retry_after""",
                    (key,window_seconds,limit+1,window_seconds)).fetchone()
                if row['request_count']>limit:
                    retry_after = row['retry_after']
                    break
        return retry_after
