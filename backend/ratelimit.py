"""A small in-memory sliding-window rate limiter.

    limiter.allow("join:1.2.3.4", limit=80, per=60)  -> True / False

It lives in the server process, which is fine because the backend runs as a
single process (see Dockerfile). Old keys are pruned by the cleanup task.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, per: float) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - per:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True

    def peek(self, key: str, limit: int, per: float) -> bool:
        """True if one more hit would still be allowed (does not record a hit)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return True
            return sum(1 for t in hits if t > now - per) < limit

    def prune(self, older_than: float = 300):
        cutoff = time.monotonic() - older_than
        with self._lock:
            for key in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                del self._hits[key]
