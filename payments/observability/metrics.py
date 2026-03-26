from __future__ import annotations

import logging
from collections import defaultdict
from threading import Lock
from typing import Mapping

logger = logging.getLogger(__name__)
_lock = Lock()
_counters = defaultdict(float)
_hist_sums = defaultdict(float)
_hist_counts = defaultdict(int)


def _tags_key(tags: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not tags:
        return tuple()
    return tuple(sorted((str(k), str(v)) for k, v in tags.items()))


def increment(name: str, value: float = 1.0, tags: Mapping[str, str] | None = None) -> None:
    key = (name, _tags_key(tags))
    with _lock:
        _counters[key] += float(value)
    logger.info("metrics.counter", extra={"metric_name": name, "metric_value": value, "metric_tags": dict(tags or {})})


def observe_ms(name: str, value_ms: float, tags: Mapping[str, str] | None = None) -> None:
    key = (name, _tags_key(tags))
    with _lock:
        _hist_sums[key] += float(value_ms)
        _hist_counts[key] += 1
    logger.info("metrics.histogram", extra={"metric_name": name, "metric_value": value_ms, "metric_tags": dict(tags or {})})


def snapshot() -> dict:
    with _lock:
        counters = {
            f"{name}|{dict(tags)}": value
            for (name, tags), value in _counters.items()
        }
        histograms = {
            f"{name}|{dict(tags)}": {
                "sum": _hist_sums[(name, tags)],
                "count": _hist_counts[(name, tags)],
            }
            for (name, tags) in _hist_counts.keys()
        }
    return {"counters": counters, "histograms": histograms}


def reset_for_tests() -> None:
    with _lock:
        _counters.clear()
        _hist_sums.clear()
        _hist_counts.clear()
