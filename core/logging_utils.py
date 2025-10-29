from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional
from contextvars import ContextVar


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        def _scrub(text: str) -> str:
            try:
                import re
                t = text or ""
                # 주민등록번호 패턴(######-#######) 및 13자리 연속 숫자 마스킹
                t = re.sub(r"\b\d{6}-\d{7}\b", "******-*******", t)
                t = re.sub(r"\b\d{13}\b", lambda m: "*" * (len(m.group(0)) - 4) + m.group(0)[-4:], t)
                return t
            except Exception:
                return text

        data: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "msg": _scrub(record.getMessage()),
        }
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)  # type: ignore[arg-type]
        # Attach request-scoped fields
        rid = get_request_id()
        if rid and not hasattr(record, "request_id"):
            data["request_id"] = rid
        for key in ("request_id", "handler", "method", "status"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        return json.dumps(data, ensure_ascii=False)


def configure_json_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    # Remove other handlers to avoid duplicate logs
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)


def maybe_enable_json_logging() -> None:
    if (os.environ.get("JSON_LOGS") or "").strip().lower() in {"1", "true", "yes", "on"}:
        configure_json_logging()


# Request-scoped context helpers
_REQUEST_ID: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(request_id: Optional[str]) -> None:
    try:
        _REQUEST_ID.set(request_id)
    except Exception:
        pass


def get_request_id() -> Optional[str]:
    try:
        return _REQUEST_ID.get()
    except Exception:
        return None
