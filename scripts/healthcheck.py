from __future__ import annotations

import json
import os
import sys
import urllib.request


def main() -> int:
    port = os.getenv("PORT", "8000")
    url = f"http://127.0.0.1:{port}/api/healthz"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # nosec - local container
            if resp.status != 200:
                return 1
            try:
                data = json.loads(resp.read().decode("utf-8"))
            except Exception:
                return 1
            return 0 if data and data.get("ok") else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())

