from __future__ import annotations

import logging
import os
import threading
import time
from typing import Protocol

from .settings import get_settings


logger = logging.getLogger("payroll_core.rate_limit")


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
    """Redis-backed rate limiter (shared across processes).

    fail_policy:
      - 'open'   → on Redis error, allow traffic (no limiting)
      - 'closed' → on Redis error, block traffic (treat as exceeded)
      - 'memory' → on Redis error, fallback to in-proc memory backend
    """

    def __init__(self, url: str, fail_policy: str = "open", fallback: _Backend | None = None) -> None:
        from redis import Redis  # type: ignore

        self._client: Redis = Redis.from_url(url, decode_responses=True)
        self._prefix = "payroll:admin:rl:"
        self._fail_policy = fail_policy
        self._fallback = fallback or InMemoryBackend()

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def increment(self, key: str, window_seconds: int) -> int:
        now = time.time()
        k = self._full_key(key)
        try:
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(k, "-inf", now - window_seconds)
            pipe.zadd(k, {str(now): now})
            pipe.zcard(k)
            pipe.expire(k, window_seconds)
            _, _, count, _ = pipe.execute()
            return int(count)
        except Exception as exc:
            policy = self._fail_policy
            logger.error("Redis rate limit error (%s): %s", policy, exc)
            if policy == "open":
                # Fail-open: behave as first hit in window
                return 1
            if policy == "closed":
                # Fail-closed: force as exceeded
                return 10**9
            # memory fallback
            return self._fallback.increment(key, window_seconds)

    def reset(self, key: str) -> None:
        try:
            self._client.delete(self._full_key(key))
        except Exception as exc:
            if self._fail_policy == "memory":
                logger.warning("Redis reset failed; using memory fallback: %s", exc)
                self._fallback.reset(key)
            else:
                logger.warning("Redis reset failed (%s): %s", self._fail_policy, exc)


class RateLimiter:
    """Facade that hides backend selection and exposes convenience helpers."""

    def __init__(self, backend: _Backend) -> None:
        self._backend = backend

    def too_many_attempts(self, key: str, window_seconds: int, max_attempts: int) -> bool:
        count = self._backend.increment(key, window_seconds)
        return count > max_attempts

    def reset(self, key: str) -> None:
        self._backend.reset(key)


_singleton: RateLimiter | None = None
_singleton_lock = threading.Lock()


def _build_backend() -> _Backend:
    settings = get_settings()
    backend = settings.admin_rate_limit_backend
    if backend == "auto":
        has_redis = bool(settings.admin_rate_limit_redis_url or os.environ.get("REDIS_URL"))
        backend = "redis" if has_redis else "memory"
        logger.debug("Rate limit backend auto-detected: %s", backend)
    if backend == "redis":
        url = settings.admin_rate_limit_redis_url or os.environ.get("REDIS_URL")
        if not url:
            raise RuntimeError("ADMIN_RATE_LIMIT_REDIS_URL (또는 REDIS_URL)이 설정되어야 Redis rate limit 백엔드를 사용할 수 있습니다.")
        try:
            policy = settings.admin_rate_limit_redis_policy
            fb = InMemoryBackend() if policy == "memory" else None
            return RedisBackend(url, fail_policy=policy, fallback=fb)
        except Exception as exc:
            raise RuntimeError(f"Redis 백엔드 초기화 실패: {exc}") from exc
    if backend == "memory":
        logger.warning("Rate limit backend falling back to in-memory. 운영 환경에서는 Redis 사용을 권장합니다.")
        return InMemoryBackend()
    raise RuntimeError(f"알 수 없는 rate limit 백엔드: {backend}")


def get_admin_rate_limiter() -> RateLimiter:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                backend = _build_backend()
                _singleton = RateLimiter(backend)
    return _singleton
