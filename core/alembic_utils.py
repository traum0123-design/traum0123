from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory


def ensure_up_to_date(engine) -> None:
    """Raise if the database revision is behind the latest Alembic head."""
    cfg_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    if not cfg_path.exists():
        raise RuntimeError(f"Alembic config not found at {cfg_path}")

    cfg = Config(str(cfg_path))
    script = ScriptDirectory.from_config(cfg)
    expected_heads = set(script.get_heads())

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_heads = set(context.get_current_heads() or [])

    if not current_heads:
        raise RuntimeError(
            "Database has no Alembic revision. Run 'alembic upgrade head' before starting the application."
        )

    if current_heads != expected_heads:
        raise RuntimeError(
            f"Alembic migration mismatch. Database heads={current_heads}, expected={expected_heads}. "
            "Apply pending migrations with 'alembic upgrade head'."
        )
