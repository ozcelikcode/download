"""Bounded Unicode-aware typo matching for SQLite catalog queries."""

import re
import unicodedata
from collections.abc import Callable
from typing import Protocol


class SQLiteFunctionConnection(Protocol):
    def create_function(self, name: str, num_params: int, function: Callable[..., int],
                        *, deterministic: bool = False) -> None: ...


def normalize(value: str) -> str:
    folded = unicodedata.normalize('NFKD', value.casefold().replace('ı', 'i'))
    return ' '.join(re.findall(r'[^\W_]+', ''.join(char for char in folded if not unicodedata.combining(char))))


def edit_distance(left: str, right: str, limit: int) -> int:
    """Bounded optimal-string-alignment distance, including adjacent transpositions."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    before_previous = previous
    for i, char in enumerate(left, 1):
        current = [i] + [limit + 1] * len(right)
        for j in range(max(1, i - limit), min(len(right), i + limit) + 1):
            current[j] = min(current[j - 1] + 1, previous[j] + 1, previous[j - 1] + (char != right[j - 1]))
            if i > 1 and j > 1 and char == right[j - 2] and left[i - 2] == right[j - 1]:
                current[j] = min(current[j], before_previous[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
        before_previous, previous = previous, current
    return previous[-1]


def search_score(title: str | None, query: str | None) -> int:
    """Rank exact phrases first; tolerate one/two edits only for meaningful words."""
    title = normalize((title or '')[:200])
    query = normalize((query or '')[:200])
    if not title or not query:
        return 0
    if query == title:
        return 100
    if query in title:
        return 95
    words = title.split()[:32]
    penalty = 0
    for term in query.split()[:12]:
        if any(term in word for word in words):
            continue
        limit = 2 if len(term) >= 6 else 1 if len(term) >= 3 else 0
        if len(term) > 48 or not limit:
            return 0
        best = min((edit_distance(term, word, limit) for word in words if len(word) <= 48), default=limit + 1)
        if best > limit:
            return 0
        penalty += best
    return max(1, 90 - penalty * 10)


def register_search_function(connection: SQLiteFunctionConnection) -> None:
    """Register on the SQLite worker connection, never process full catalogs in a route."""
    connection.create_function('download_search_score', 2, search_score, deterministic=True)
