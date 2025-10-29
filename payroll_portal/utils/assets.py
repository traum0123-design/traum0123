from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict


@lru_cache(maxsize=1)
def _load_manifest() -> Dict[str, str]:
    root = Path(__file__).resolve().parents[1] / "static"
    manifest_path = root / "dist" / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def resolve_static(path: str) -> str:
    path = str(path).lstrip("/")
    manifest = _load_manifest()
    mapped = manifest.get(path)
    return mapped or path


def clear_manifest_cache() -> None:
    _load_manifest.cache_clear()  # type: ignore[attr-defined]

