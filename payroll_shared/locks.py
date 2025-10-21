from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from typing import Iterator, Optional

from redis import Redis  # type: ignore

_DEFAULT_PREFIX = "payroll:lock:"


def _redis_client() -> Optional[Redis]:
    url = (
        os.environ.get("LOCK_REDIS_URL")
        or os.environ.get("REDIS_URL")
        or os.environ.get("ADMIN_RATE_LIMIT_REDIS_URL")
    )
    if not url:
        return None
    try:
        return Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


@contextmanager
def redis_lock(
    name: str,
    ttl_seconds: int = 30,
    wait_timeout: int = 10,
    sleep_seconds: float = 0.25,
) -> Iterator[bool]:
    """Context manager that acquires a Redis-backed lock.

    Args:
        name: Unique lock key (without prefix).
        ttl_seconds: Lock expiration to avoid deadlocks.
        wait_timeout: Maximum seconds to wait for acquisition.
        sleep_seconds: Delay between acquisition attempts.

    Yields:
        bool indicating whether the lock was successfully acquired.
    """

    client = _redis_client()
    if client is None:
        # Redis unavailable → treat as no-op lock (caller should handle race fallback)
        yield False
        return

    token = uuid.uuid4().hex
    key = f"{_DEFAULT_PREFIX}{name}"
    deadline = time.monotonic() + max(wait_timeout, 0)
    acquired = False
    try:
        while time.monotonic() < deadline:
            if client.set(key, token, nx=True, ex=ttl_seconds):
                acquired = True
                break
            time.sleep(max(sleep_seconds, 0.05))
        yield acquired
    finally:
        if acquired:
            try:
                script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                end
                return 0
                """
                client.eval(script, 1, key, token)
            except Exception:
                pass

