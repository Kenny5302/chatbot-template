import smtplib

from app.config import Settings
from app.emailer import GmailEmailer, build_lead_email

LEAD = {"name": "Maria Lopez", "phone": "530-555-0111", "problem": "Brakes squeal",
        "best_time_to_call": "tomorrow", "vehicle_or_equipment": "", "language": "en"}


def make(tmp_path, fail_times, sleeps):
    settings = Settings(gmail_address="a@b.co", gmail_app_password="x", data_dir=tmp_path)
    emailer = GmailEmailer(settings, sleep=sleeps.append)
    state = {"calls": 0}

    def fake_send(msg):
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise smtplib.SMTPServerDisconnected("boom")
    emailer._send_once = fake_send  # type: ignore[method-assign]
    return emailer, state


def test_retries_then_succeeds(tmp_path, auto):
    sleeps: list[float] = []
    emailer, state = make(tmp_path, 2, sleeps)
    emailer.send_lead(auto, LEAD, "abc")
    assert state["calls"] == 3 and len(sleeps) == 2
    assert not (tmp_path / auto.slug / "unsent_leads.log").exists()


def test_gives_up_after_three_tries_and_writes_unsent_log(tmp_path, auto, caplog):
    sleeps: list[float] = []
    emailer, state = make(tmp_path, 99, sleeps)
    with caplog.at_level("ERROR"):
        emailer.send_lead(auto, LEAD, "abc123")
    assert state["calls"] == 3 and len(sleeps) == 2  # no wait after the last try
    assert any("LEAD EMAIL NOT SENT" in m for m in caplog.messages)
    line = (tmp_path / auto.slug / "unsent_leads.log").read_text()
    assert "lead_id=abc123" in line and "SMTPServerDisconnected" in line and line.count("\n") == 1


def test_updated_email_subject_and_changes(auto):
    settings = Settings(gmail_address="a@b.co")
    new = {**LEAD, "phone": "530-555-0222"}
    msg = build_lead_email(settings, auto, new, "abc", previous=LEAD)
    body = msg.get_content()
    assert str(msg["Subject"]).startswith("Updated lead")
    assert "Phone: 530-555-0222" in body and "530-555-0111 -> 530-555-0222" in body
    assert str(build_lead_email(settings, auto, LEAD, "abc")["Subject"]).startswith("New lead")
