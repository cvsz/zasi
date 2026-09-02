"""Small authenticated Redis runtime used for shared request coordination."""

from __future__ import annotations

import time
from typing import Any, Tuple

from .identity import hash_token


_FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCRBY', KEYS[1], 1)
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


class RedisRuntime:
    """Authenticated Redis client with a fail-closed shared rate limiter."""

    def __init__(self, redis_url: str):
        if not redis_url:
            raise ValueError("redis_url is required")
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("Redis profiles require the redis package") from exc
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def consume_rate_limit(
        self,
        tenant_id: str,
        subject: str,
        limit: int,
        window_seconds: int,
    ) -> Tuple[bool, int]:
        if not subject or not 1 <= limit <= 1_000_000 or not 1 <= window_seconds <= 86_400:
            raise ValueError("invalid rate limit configuration")
        now_seconds = int(time.time())
        bucket = now_seconds // window_seconds
        reset_epoch = (bucket + 1) * window_seconds
        key = "zasi:ratelimit:" + hash_token(f"{tenant_id}:{subject}:{bucket}")
        try:
            count = int(
                self._client.eval(
                    _FIXED_WINDOW_SCRIPT,
                    1,
                    key,
                    str(window_seconds),
                )
            )
        except Exception as exc:
            raise RuntimeError("shared Redis rate limiter is unavailable") from exc
        return count <= limit, max(0, reset_epoch - now_seconds)

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            close()

    @property
    def client(self) -> Any:
        """Expose the authenticated client for health/maintenance integrations."""
        return self._client
