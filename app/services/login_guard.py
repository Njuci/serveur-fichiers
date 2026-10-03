"""Limitation des tentatives de connexion (anti brute-force), en mémoire."""

import threading
import time
from collections import defaultdict, deque

from .. import config


class LoginGuard:
    """Bloque une clé (IP + nom d'utilisateur) après trop d'échecs récents."""

    def __init__(
        self,
        max_failures: int = config.LOGIN_MAX_FAILURES,
        window_seconds: float = config.LOGIN_WINDOW_SECONDS,
        clock=time.monotonic,
    ):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _purge(self, key: str) -> deque[float]:
        attempts = self._failures[key]
        limit = self._clock() - self.window_seconds
        while attempts and attempts[0] < limit:
            attempts.popleft()
        if not attempts:
            self._failures.pop(key, None)
        return attempts

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._purge(key)) >= self.max_failures

    def register_failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(self._clock())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
