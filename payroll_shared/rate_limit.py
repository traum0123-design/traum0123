from __future__ import annotations

import os
import threading
import time
from typing import Optional, Protocol

from .settings import get_settings


class _Backend(Protocol):
    def increment(self, key: str, window_seconds: int) -> int:
        ...

    def reset(self, key: str) -> None:
        ...


class InMemoryBackend:
    """Process-local in-memory rate limit storage."""

    def __init__(self) -> None:
        self._store: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def increment(self, key: str, window_seconds: int) -> int:
        now = time.time()
        with self._lock:
            hits = [ts for ts in self._store.get(key, []) if now - ts <= window_seconds]
            hits.append(now)
            self._store[key] = hits
            return len(hits)

    def reset(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


class RedisBackend:
    """Redis-backed rate limiter (shared across processes)."""

    def __init__(self, url: str) -> None:
        from redis import Redis  # type: ignore

        self._client: Redis = Redis.from_url(url, decode_responses=True)
        self._prefix = "payroll:admin:rl:"

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def increment(self, key: str, window_seconds: int) -> int:
        now = time.time()
        k = self._full_key(key)
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(k, "-inf", now - window_seconds)
        pipe.zadd(k, {str(now): now})
        pipe.zcard(k)
        pipe.expire(k, window_seconds)
        _, _, count, _ = pipe.execute()
        return int(count)

    def reset(self, key: str) -> None:
        self._client.delete(self._full_key(key))


class RateLimiter:
    """Facade that hides backend selection and exposes convenience helpers."""

    def __init__(self, backend: _Backend) -> None:
        self._backend = backend

    def too_many_attempts(self, key: str, window_seconds: int, max_attempts: int) -> bool:
        count = self._backend.increment(key, window_seconds)
        return count > max_attempts

    def reset(self, key: str) -> None:
        self._backend.reset(key)


_singleton: Optional[RateLimiter] = None
_singleton_lock = threading.Lock()


def _build_backend() -> _Backend:
    settings = get_settings()
    backend = settings.admin_rate_limit_backend
    if backend == "redis":
        url = settings.admin_rate_limit_redis_url or os.environ.get("REDIS_URL")
        if not url:
            raise RuntimeError("ADMIN_RATE_LIMIT_REDIS_URL (또는 REDIS_URL)이 설정되어야 Redis rate limit 백엔드를 사용할 수 있습니다.")
        try:
            return RedisBackend(url)
        except Exception as exc:
            raise RuntimeError(f"Redis 백엔드 초기화 실패: {exc}") from exc
    return InMemoryBackend()


def get_admin_rate_limiter() -> RateLimiter:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                backend = _build_backend()
                _singleton = RateLimiter(backend)
    return _singleton
