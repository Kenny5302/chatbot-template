"""Validate a save_lead tool call, store it, and email it in the background."""

import re
import threading
from typing import Any, Callable

from app.businesses import Business
from app.emailer import GmailEmailer
from app.storage import FileStorage


def _run_in_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True).start()


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def validate_lead(raw: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Returns (clean_lead, "") or (None, error message the model can act on)."""
    lead = {
        "name": _clean(raw.get("name"), 100),
        "phone": _clean(raw.get("phone"), 40),
        "problem": _clean(raw.get("problem"), 1000),
        "best_time_to_call": _clean(raw.get("best_time_to_call"), 200),
        "vehicle_or_equipment": _clean(raw.get("vehicle_or_equipment"), 200),
        "language": raw.get("language") if raw.get("language") in ("en", "es", "pa") else "en",
    }
    for field in ("name", "problem", "best_time_to_call"):
        if not lead[field]:
            return None, f"Missing {field.replace('_', ' ')}. Ask the customer for it."
    digits = re.sub(r"\D", "", lead["phone"])
    if not 10 <= len(digits) <= 15:
        return None, "The phone number doesn't look complete (need at least 10 digits). Ask the customer to confirm it."
    return lead, ""


class LeadService:
    def __init__(self, storage: FileStorage, emailer: GmailEmailer, run: Callable[[Callable[[], None]], None] = _run_in_thread):
        self.storage = storage
        self.emailer = emailer
        self.run = run

    def submit(self, business: Business, raw: dict[str, Any], conversation_id: str) -> tuple[bool, str]:
        lead, error = validate_lead(raw)
        if lead is None:
            return False, error
        lead["conversation_id"] = conversation_id
        lead_id = self.storage.save_lead(business.slug, lead)
        self.run(lambda: self.emailer.send_lead(business, lead, lead_id))
        return True, (
            f"Lead saved (id {lead_id}). Tell the customer you've passed their details to the team and that we'll "
            "aim to call around the time they asked for, or as soon as we can. Do not promise an exact time."
        )
