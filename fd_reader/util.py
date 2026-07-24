"""Small generic helpers with no domain knowledge, shared across
parsing/match/report."""
from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from typing import TypeVar

T = TypeVar("T")
K = TypeVar("K", bound=Hashable)


def group_by(items: Iterable[T], key_fn: Callable[[T], K]) -> dict[K, list[T]]:
    """Bucket items into a dict of lists by key_fn(item), preserving
    each bucket's original relative order."""
    result: dict[K, list[T]] = {}
    for item in items:
        result.setdefault(key_fn(item), []).append(item)
    return result
