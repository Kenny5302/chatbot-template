"""Lead emails through Gmail SMTP with an app password."""

import logging
import re
import smtplib
from email.message import EmailMessage

from app.businesses import Business
from app.config import Settings

log = logging.getLogger(__name__)


def _one_line(text: str, limit: int = 80) -> str:
    return re.sub(r"\s+", " ", text).strip()[:limit]


def build_lead_email(settings: Settings, business: Business, lead: dict, lead_id: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.gmail_address
    msg["To"] = business.lead_email
    if settings.operator_bcc_email:
        msg["Bcc"] = settings.operator_bcc_email
    msg["Subject"] = f"New lead for {business.name}: {_one_line(lead['name'], 40)} - {_one_line(lead['problem'], 50)}"
    lines = [
        f"New customer lead from the {business.name} chat assistant.",
        "",
        f"Name: {lead['name']}",
        f"Phone: {lead['phone']}",
        f"Problem: {lead['problem']}",
        f"Best time to call: {lead['best_time_to_call']}",
    ]
    if lead.get("vehicle_or_equipment"):
        lines.append(f"Vehicle/equipment: {lead['vehicle_or_equipment']}")
    lines += [
        f"Customer language: {lead.get('language', 'en')}",
        "",
        f"Lead ID: {lead_id}",
    ]
    msg.set_content("\n".join(lines))
    return msg


class GmailEmailer:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.gmail_address and self.settings.gmail_app_password)

    def send_lead(self, business: Business, lead: dict, lead_id: str) -> None:
        if not self.configured:
            log.warning("Gmail not configured; lead %s saved to disk but not emailed", lead_id)
            return
        msg = build_lead_email(self.settings, business, lead, lead_id)
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
                smtp.login(self.settings.gmail_address, self.settings.gmail_app_password)
                smtp.send_message(msg)  # also delivers to the Bcc address, then strips the header
        except (smtplib.SMTPException, OSError):
            log.exception("Failed to email lead %s for %s", lead_id, business.slug)
