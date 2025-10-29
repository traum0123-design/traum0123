from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Dict, Tuple


_lock = threading.Lock()
_count: Dict[Tuple[str, str, int], int] = defaultdict(int)
_buckets = [
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
]
_hist_count: Dict[Tuple[str, str], int] = defaultdict(int)
_hist_sum: Dict[Tuple[str, str], float] = defaultdict(float)
_hist_buckets: Dict[Tuple[str, str, float], int] = defaultdict(int)


def observe_request(handler: str, method: str, status: int, duration_s: float) -> None:
    key = (handler, method.upper(), int(status))
    hkey = (handler, method.upper())
    with _lock:
        _count[key] += 1
        _hist_count[hkey] += 1
        _hist_sum[hkey] += float(duration_s)
        placed = False
        for le in _buckets:
            if duration_s <= le:
                _hist_buckets[(handler, method.upper(), le)] += 1
                placed = True
        if not placed:
            # +Inf bucket
            _hist_buckets[(handler, method.upper(), float("inf"))] += 1


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def export_prometheus() -> str:
    lines = []
    lines.append("# HELP payroll_request_total Total HTTP requests")
    lines.append("# TYPE payroll_request_total counter")
    with _lock:
        for (handler, method, status), val in sorted(_count.items()):
            lines.append(
                f'payroll_request_total{{handler="{_esc(handler)}",method="{_esc(method)}",status="{int(status)}"}} {int(val)}'
            )

        lines.append("# HELP payroll_request_duration_seconds Request duration histogram")
        lines.append("# TYPE payroll_request_duration_seconds histogram")
        # Group by handler/method
        by_pair: Dict[Tuple[str, str], None] = {k: None for k in _hist_count.keys()}
        for handler, method in sorted(by_pair.keys()):
            cumulative = 0
            for le in _buckets:
                bucket_count = _hist_buckets.get((handler, method, le), 0)
                cumulative += bucket_count
                lines.append(
                    f'payroll_request_duration_seconds_bucket{{handler="{_esc(handler)}",method="{_esc(method)}",le="{le}"}} {int(cumulative)}'
                )
            # +Inf bucket
            inf_count = _hist_buckets.get((handler, method, float("inf")), 0)
            cumulative += inf_count
            lines.append(
                f'payroll_request_duration_seconds_bucket{{handler="{_esc(handler)}",method="{_esc(method)}",le="+Inf"}} {int(cumulative)}'
            )
            lines.append(
                f'payroll_request_duration_seconds_sum{{handler="{_esc(handler)}",method="{_esc(method)}"}} {float(_hist_sum.get((handler, method), 0.0))}'
            )
            lines.append(
                f'payroll_request_duration_seconds_count{{handler="{_esc(handler)}",method="{_esc(method)}"}} {int(_hist_count.get((handler, method), 0))}'
            )
    return "\n".join(lines) + "\n"

