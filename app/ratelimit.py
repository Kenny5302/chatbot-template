"""Per-visitor sliding-window rate limit (in memory: fine for one server instance)."""

import hashlib
import ipaddress
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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


class DailyCap:
    """Counts chat messages per business per day and across all businesses (in memory, so a restart
    resets the counts; the per-visitor limits and the Anthropic console spend limit still apply)."""

    def __init__(self, global_limit: int):
        self.global_limit = global_limit
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        self._warned: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def try_acquire(self, slug: str, limit: int, tz: str, now: datetime | None = None) -> str | None:
        """Count one message. Returns None if allowed, else which cap was hit ('business' or 'global')."""
        now = now or datetime.now(timezone.utc)
        biz_key = (slug, f"{now.astimezone(ZoneInfo(tz)):%Y-%m-%d}")  # the shop's own calendar day
        all_key = ("*", f"{now:%Y-%m-%d}")
        with self._lock:
            for scope, key, cap in (("business", biz_key, limit), ("global", all_key, self.global_limit)):
                if self._counts[key] >= cap:
                    return scope
            self._counts[biz_key] += 1
            self._counts[all_key] += 1
            return None

    def first_warning(self, slug: str, scope: str, now: datetime | None = None) -> bool:
        """True the first time a cap is reported on a given day, so the log gets one warning per day."""
        now = now or datetime.now(timezone.utc)
        key = (slug if scope == "business" else "*", f"{now:%Y-%m-%d}")
        with self._lock:
            if key in self._warned:
                return False
            self._warned = {k for k in self._warned if k[1] == key[1]}  # forget earlier days
            self._warned.add(key)
            return True
