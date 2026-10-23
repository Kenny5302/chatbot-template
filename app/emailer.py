"""Lead emails through Gmail SMTP with an app password."""

import logging
import re
import smtplib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from email.message import EmailMessage

from app.businesses import Business
from app.config import Settings

log = logging.getLogger(__name__)


def _one_line(text: str, limit: int = 80) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


SEND_ATTEMPTS = 3
RETRY_WAITS = (2.0, 6.0)  # seconds to wait after the 1st and 2nd failed try

FIELD_LABELS = {
    "name": "Name", "phone": "Phone", "problem": "Problem", "best_time_to_call": "Best time to call",
    "vehicle_or_equipment": "Vehicle/equipment", "language": "Customer language",
}


def build_lead_email(
    settings: Settings, business: Business, lead: dict, lead_id: str, previous: dict | None = None
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.gmail_address
    msg["To"] = business.lead_email
    if settings.operator_bcc_email:
        msg["Bcc"] = settings.operator_bcc_email
    updated = previous is not None
    msg["Subject"] = f"{'Updated lead' if updated else 'New lead'} for {business.name}: {_one_line(lead['name'], 40)} - {_one_line(lead['problem'], 50)}"
    lines = [
        (f"The customer corrected their details in the {business.name} chat assistant."
         if updated else f"New customer lead from the {business.name} chat assistant."),
        "",
        f"Name: {lead['name']}",
        f"Phone: {lead['phone']}",
        f"Problem: {lead['problem']}",
        f"Best time to call: {lead['best_time_to_call']}",
    ]
    if lead.get("vehicle_or_equipment"):
        lines.append(f"Vehicle/equipment: {lead['vehicle_or_equipment']}")
    lines.append(f"Customer language: {lead.get('language', 'en')}")
    if previous is not None:
        changed = [k for k in FIELD_LABELS if (previous.get(k) or "") != (lead.get(k) or "")]
        lines += ["", "What changed:"]
        lines += [f"- {FIELD_LABELS[k]}: {previous.get(k) or '(none)'} -> {lead.get(k) or '(none)'}" for k in changed]
    lines += ["", f"Lead ID: {lead_id}"]
    msg.set_content("\n".join(lines))
    return msg


class GmailEmailer:
    def __init__(self, settings: Settings, sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self.sleep = sleep

    @property
    def configured(self) -> bool:
        return bool(self.settings.gmail_address and self.settings.gmail_app_password)

    def _send_once(self, msg: EmailMessage) -> None:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(self.settings.gmail_address, self.settings.gmail_app_password)
            smtp.send_message(msg)  # also delivers to the Bcc address, then strips the header

    def _record_unsent(self, business: Business, lead_id: str, subject: str, reason: str) -> None:
        """Leave a line the owner can find: the lead itself is still in data/<slug>/leads/."""
        try:
            path = Path(self.settings.data_dir) / business.slug / "unsent_leads.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with path.open("a", encoding="utf-8") as f:
                f.write(f"{now} lead_id={lead_id} reason={reason} subject={subject!r}\n")
        except OSError:
            log.exception("Could not write unsent_leads.log for %s", business.slug)

    def send_lead(self, business: Business, lead: dict, lead_id: str, previous: dict | None = None) -> None:
        msg = build_lead_email(self.settings, business, lead, lead_id, previous)
        subject = str(msg["Subject"])
        if not self.configured:
            log.warning("Gmail not configured; lead %s saved to disk but not emailed", lead_id)
            self._record_unsent(business, lead_id, subject, "gmail not configured")
            return
        error = ""
        for attempt in range(1, SEND_ATTEMPTS + 1):
            try:
                self._send_once(msg)
                return
            except (smtplib.SMTPException, OSError) as e:
                error = type(e).__name__
                log.warning("Email attempt %d/%d failed for lead %s (%s): %s", attempt, SEND_ATTEMPTS, lead_id, business.slug, error)
                if attempt < SEND_ATTEMPTS:
                    self.sleep(RETRY_WAITS[min(attempt, len(RETRY_WAITS)) - 1])
        log.error("LEAD EMAIL NOT SENT after %d tries: lead %s for %s (%s). The lead is saved in %s/%s/leads/.",
                  SEND_ATTEMPTS, lead_id, business.slug, error, self.settings.data_dir, business.slug)
        self._record_unsent(business, lead_id, subject, f"{SEND_ATTEMPTS} send attempts failed: {error}")
