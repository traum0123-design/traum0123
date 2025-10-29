from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parents[1] / "payroll_portal" / "static"
DIST_DIR = SOURCE_DIR / "dist"


def content_hash(path: Path, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:10]


def should_fingerprint(path: Path) -> bool:
    if path.suffix.lower() in {".js", ".css"}:
        # do not include already built files
        return "dist" not in str(path)
    return False


def rel_from_source(path: Path) -> str:
    return str(path.relative_to(SOURCE_DIR)).replace("\\", "/")


def build() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for p in SOURCE_DIR.rglob("*"):
        if p.is_file() and should_fingerprint(p):
            rel = rel_from_source(p)
            h = content_hash(p)
            target_name = f"{p.stem}.{h}{p.suffix}"
            # Place in same relative directory under dist/
            subdir = p.parent.relative_to(SOURCE_DIR)
            out_dir = DIST_DIR / subdir
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / target_name
            shutil.copy2(str(p), str(out_path))
            manifest[rel] = str(Path("dist") / subdir / target_name).replace("\\", "/")
    (DIST_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Built {len(manifest)} assets → {DIST_DIR}/manifest.json")


if __name__ == "__main__":
    build()

