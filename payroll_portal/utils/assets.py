from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _load_manifest() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1] / "static"
    manifest_candidates = [
        root / "dist" / "manifest.json",
        root / "dist" / ".vite" / "manifest.json",
    ]
    manifest_path = next((p for p in manifest_candidates if p.exists()), None)
    if not manifest_path:
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}

    # build_static.py format: {"styles.css": "dist/styles.<hash>.css", ...}
    if all(isinstance(v, str) for v in data.values()):
        return {str(k): str(v) for k, v in data.items()}

    # Vite manifest format: {"payroll_portal/static/styles.css": {"file": "assets/...", "src": "...", ...}, ...}
    manifest: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        out_file = value.get("file")
        if not out_file:
            continue
        out_path = str(out_file).replace("\\", "/")
        if not out_path.startswith("dist/"):
            out_path = f"dist/{out_path}"

        src = value.get("src") or key
        src_path = str(src).replace("\\", "/").lstrip("/")
        for prefix in ("payroll_portal/static/", "static/"):
            if src_path.startswith(prefix):
                src_path = src_path[len(prefix) :]
                break
        manifest[src_path] = out_path
    return manifest


def resolve_static(path: str) -> str:
    path = str(path).lstrip("/")
    manifest = _load_manifest()
    mapped = manifest.get(path)
    return mapped or path


def clear_manifest_cache() -> None:
    _load_manifest.cache_clear()  # type: ignore[attr-defined]
