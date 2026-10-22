from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import Request

from app.businesses import BusinessFileError, load_all, load_business
from app.hours import get_status, status_line
from app.leads import validate_lead
from app.prompts import LANGUAGE_NOTES, build_system_prompt, greeting_lines, language_hint
from app.ratelimit import RateLimiter, client_ip, visitor_hash

PT = ZoneInfo("America/Los_Angeles")


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=PT)


# ---- business files -----------------------------------------------------
def test_demo_businesses_load(businesses):
    assert set(businesses) == {"feather-river-auto", "sutter-buttes-hvac"}
    assert businesses["feather-river-auto"].model == "claude-haiku-5-5"


def test_bad_yaml_names_the_file(tmp_path):
    bad = tmp_path / "oops.yaml"
    bad.write_text("name: X\nphone: '1'\nlead_email: nope\nlocation: {address: a}\nhours: {mon: '9-5'}\n")
    with pytest.raises(BusinessFileError, match="oops.yaml"):
        load_business(bad)


def test_unknown_key_rejected(tmp_path):
    f = tmp_path / "typo.yaml"
    f.write_text("name: X\nphone: '1'\nlead_email: a@b.co\nlocation: {address: a}\nhours: {mon: '9:00-17:00'}\nservicez: []\n")
    with pytest.raises(BusinessFileError):
        load_business(f)


def test_draft_files_are_skipped(tmp_path):
    (tmp_path / "x.draft.yaml").write_text("not: valid")
    assert load_all(tmp_path) == {}


# ---- hours --------------------------------------------------------------
def test_open_and_closed(auto):
    assert get_status(auto, at(2026, 10, 21, 10, 0)).is_open            # Wed morning
    assert not get_status(auto, at(2026, 10, 21, 17, 30)).is_open       # closing time itself is closed
    sat = get_status(auto, at(2026, 10, 24, 14, 0))                     # Saturday after 1pm
    assert not sat.is_open and sat.next_open_label == "Mon 8:00 AM"


def test_holiday_and_utc_input(auto):
    assert not get_status(auto, at(2026, 11, 26, 10, 0)).is_open
    utc = datetime(2026, 10, 21, 17, 0, tzinfo=ZoneInfo("UTC"))         # 10:00 Pacific
    assert get_status(auto, utc).is_open


def test_status_line_text(auto):
    line = status_line(auto, at(2026, 10, 25, 11, 0))
    assert "CLOSED" in line and "Next opens Mon 8:00 AM" in line
    assert "Punjabi" in status_line(auto, at(2026, 10, 25, 11, 0), language_hint="reply in Punjabi")


# ---- prompt rules -------------------------------------------------------
def test_greeting_is_english_plus_one_short_language_line(auto, businesses):
    lines = greeting_lines(auto)
    assert len(lines) == 2
    assert "virtual assistant" in lines[0] and "AI" in lines[0] and "Feather River Auto Repair" in lines[0]
    assert lines[1] == "Hablamos español · ਪੰਜਾਬੀ ਵੀ ਬੋਲਦੇ ਹਾਂ" and len(lines[1]) < 60
    assert greeting_lines(businesses["sutter-buttes-hvac"])[1] == "Hablamos español"
    assert set(LANGUAGE_NOTES) == {"es", "pa"}


def test_english_only_business_gets_just_the_greeting(auto):
    only_en = auto.model_copy(update={"languages": ["en"]})
    assert len(greeting_lines(only_en)) == 1


def test_language_hint_detects_gurmukhi_only():
    assert "Gurmukhi" in language_hint("ਤੁਸੀਂ ਸ਼ਨੀਵਾਰ ਨੂੰ ਖੁੱਲ੍ਹੇ ਹੋ?")
    assert "Gurmukhi" in language_hint("ਮੇਰੀ Honda ਦੀਆਂ ਬ੍ਰੇਕਾਂ ਠੀਕ ਕਰ ਦਿਓਗੇ?")   # car name in Latin letters is still Punjabi
    assert language_hint("ਕੀ you are open on Saturday?") == ""                   # mostly English: no hint
    assert language_hint("Are you open Saturday?") == ""
    assert language_hint("¿Abren los sábados?") == ""


def test_emergency_rule_is_first(auto):
    prompt = build_system_prompt(auto)
    first_rule = prompt.index("RULE 1")
    for keyword in ("gas", "smoke", "carbon monoxide", "brakes failing", "overheating", "911"):
        assert keyword.lower() in prompt.lower()
    assert first_rule < prompt.index("RULE 2") < prompt.index("RULE 3") < prompt.index("ABOUT FEATHER RIVER")
    assert "SAFETY FIRST" in prompt[:first_rule + 120]


def test_no_promises_rule(auto):
    prompt = build_system_prompt(auto)
    for phrase in ("discounts", "price matches", "ignore these instructions", "estimate"):
        assert phrase in prompt


def test_on_topic_rule(auto):
    prompt = build_system_prompt(auto)
    for phrase in ("coding", "homework", "essays", "roleplay", "Never write code", "not something you can share"):
        assert phrase in prompt


def test_speak_naturally_rule(auto):
    prompt = build_system_prompt(auto)
    assert "business file" not in prompt.lower()
    for phrase in ("We work on most domestic, Asian, and European cars", '"the file"', '"my information"', '"my instructions"'):
        assert phrase in prompt


def test_callback_only_when_needed_rule(auto):
    prompt = build_system_prompt(auto)
    assert "Do not end replies with an offer of a callback" in prompt
    assert "do not repeat the phone number in every reply" in prompt
    for trigger in ("(a) you can't answer", "(b) we are closed", "(c) it's an emergency", "(d) the customer asks"):
        assert trigger in prompt


def test_language_rule_covers_gurmukhi_and_the_english_note(auto):
    prompt = build_system_prompt(auto)
    assert "Gurmukhi" in prompt and "language and script of the customer's latest message" in prompt
    assert "(always English) says nothing about the customer's language" in prompt


def test_lead_confirmation_makes_no_exact_time_promise(auto):
    prompt = build_system_prompt(auto)
    assert "Never promise an exact callback time" in prompt and "as soon as we can" in prompt


def test_prompt_has_business_facts_but_not_lead_email(auto):
    prompt = build_system_prompt(auto)
    assert "(530) 555-0142" in prompt and "Check engine light" in prompt
    assert auto.lead_email not in prompt


def test_prompt_is_stable_between_calls(auto):
    assert build_system_prompt(auto) == build_system_prompt(auto)  # required for prompt caching


# ---- leads --------------------------------------------------------------
def test_validate_lead():
    ok, err = validate_lead({"name": "A", "phone": "(530) 555-0111", "problem": "p", "best_time_to_call": "now"})
    assert ok and not err
    bad, err = validate_lead({"name": "A", "phone": "555", "problem": "p", "best_time_to_call": "now"})
    assert bad is None and "phone" in err
    bad, err = validate_lead({"name": "", "phone": "5305550111", "problem": "p", "best_time_to_call": "now"})
    assert bad is None and "name" in err


# ---- rate limit and client IP -------------------------------------------
def make_request(headers=None, client=("10.0.0.9", 1234)):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": client, "method": "GET", "path": "/", "query_string": b""})


def test_client_ip_uses_rightmost_entry_added_by_proxy():
    # Anything to the left of the proxy's entry is client-supplied and must be ignored.
    req = make_request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8, 203.0.113.7"})
    assert client_ip(req) == "203.0.113.7"


def test_client_ip_cannot_be_spoofed_by_client_header():
    real = "203.0.113.7"
    for fake in ("9.9.9.9", "10.0.0.1, 10.0.0.2", "198.51.100.4"):
        assert client_ip(make_request({"X-Forwarded-For": f"{fake}, {real}"})) == real


def test_client_ip_single_entry():
    assert client_ip(make_request({"X-Forwarded-For": "203.0.113.7"})) == "203.0.113.7"


def test_client_ip_with_two_trusted_proxies():
    req = make_request({"X-Forwarded-For": "6.6.6.6, 203.0.113.7, 172.16.0.5"})
    assert client_ip(req, trusted_hops=2) == "203.0.113.7"


def test_client_ip_falls_back_to_direct_client():
    assert client_ip(make_request()) == "10.0.0.9"
    assert client_ip(make_request({"X-Forwarded-For": "not-an-ip"})) == "10.0.0.9"
    assert client_ip(make_request({"X-Forwarded-For": "1.2.3.4, junk"})) == "10.0.0.9"
    assert client_ip(make_request({"X-Forwarded-For": ""})) == "10.0.0.9"
    # header shorter than the number of trusted proxies: can't trust it
    assert client_ip(make_request({"X-Forwarded-For": "203.0.113.7"}), trusted_hops=2) == "10.0.0.9"


def test_client_ip_ignores_header_when_hops_is_zero():
    assert client_ip(make_request({"X-Forwarded-For": "203.0.113.7"}), trusted_hops=0) == "10.0.0.9"


def test_rate_limiter_blocks_and_recovers():
    rl = RateLimiter(per_minute=3, per_day=100)
    assert [rl.check("a", now=t) for t in (0, 1, 2)] == [0, 0, 0]
    assert rl.check("a", now=3) > 0
    assert rl.check("b", now=3) == 0                 # other visitors unaffected
    assert rl.check("a", now=62) == 0                # window slid past the first hits


def test_daily_limit():
    rl = RateLimiter(per_minute=100, per_day=5)
    for i in range(5):
        assert rl.check("a", now=i * 100) == 0
    assert rl.check("a", now=600) > 0


def test_visitor_hash_hides_ip():
    h = visitor_hash("203.0.113.7", "salt")
    assert "203" not in h and h == visitor_hash("203.0.113.7", "salt") != visitor_hash("203.0.113.8", "salt")
