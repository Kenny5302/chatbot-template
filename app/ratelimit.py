"""Per-visitor sliding-window rate limit (in memory: fine for one server instance)."""

import hashlib
import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import Request


def client_ip(request: Request, trusted_hops: int = 1) -> str:
    """Visitor IP for rate limiting.

    Each proxy appends the address it received the request from to X-Forwarded-For, so everything to the
    left of the entries our own proxies added is client-controlled and can be spoofed. We therefore count
    from the right: with trusted_hops=1 we use the last entry (added by the proxy directly in front of us).
    Use 2 if a second proxy sits in between, and 0 to ignore the header (no proxy, e.g. local dev).
    If the header is missing, too short, or not an IP, fall back to the direct connection.
    """
    direct = request.client.host if request.client else "unknown"
    if trusted_hops < 1:
        return direct
    entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
    if len(entries) < trusted_hops:
        return direct
    try:
        return str(ipaddress.ip_address(entries[-trusted_hops]))
    except ValueError:
        return direct


def visitor_hash(ip: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:16]


class RateLimiter:
    def __init__(self, per_minute: int, per_day: int):
        self.windows = ((per_minute, 60.0), (per_day, 86400.0))
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> int:
        """Record a hit. Returns 0 if allowed, otherwise seconds until the visitor may retry."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            longest = self.windows[-1][1]
            while hits and now - hits[0] > longest:
                hits.popleft()
            for limit, span in self.windows:
                recent = [t for t in hits if now - t <= span]
                if len(recent) >= limit:
                    return max(1, int(recent[0] + span - now) + 1)
            hits.append(now)
            if len(self._hits) > 10000:  # drop idle visitors so memory can't grow without bound
                for k in [k for k, d in self._hits.items() if not d or now - d[-1] > longest]:
                    del self._hits[k]
            return 0
