from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import Request

from app.businesses import BusinessFileError, load_all, load_business
from app.hours import get_status, status_line
from app.leads import validate_lead
from app.i18n import BUTTON_LABELS, STRINGS, SUPPORTED, default_language, pick_language, text, ui_for
from app.prompts import build_system_prompt, language_hint, language_note
from app.ratelimit import RateLimiter, client_ip, visitor_hash

PT = ZoneInfo("America/Los_Angeles")


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=PT)


# ---- business files -----------------------------------------------------
def test_demo_businesses_load(businesses):
    assert set(businesses) == {"feather-river-auto", "sutter-buttes-hvac"}
    assert businesses["feather-river-auto"].model == "claude-haiku-5-5"


def test_not_offered_is_optional_and_loaded(auto, businesses, tmp_path):
    assert "diesel trucks over 10,000 lbs" in auto.not_offered and "RVs and motorhomes" in auto.not_offered
    assert "plumbing" in businesses["sutter-buttes-hvac"].not_offered
    f = tmp_path / "plain.yaml"
    f.write_text("name: X\nphone: '1'\nlead_email: a@b.co\nlocation: {address: a}\nhours: {mon: '9:00-17:00'}\n")
    assert load_business(f).not_offered == []           # optional: existing files keep working


def test_not_offered_rejects_blank_entries_and_non_lists(tmp_path):
    base = "name: X\nphone: '1'\nlead_email: a@b.co\nlocation: {address: a}\nhours: {mon: '9:00-17:00'}\n"
    for bad in ("not_offered: ['RVs', '  ']\n", "not_offered: RVs\n"):
        f = tmp_path / "bad.yaml"
        f.write_text(base + bad)
        with pytest.raises(BusinessFileError, match="bad.yaml"):
            load_business(f)


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
# ---- translations (app/i18n.py) ---------------------------------------
def test_every_language_has_every_string():
    assert set(STRINGS) == set(SUPPORTED) == set(BUTTON_LABELS)
    english_keys = set(STRINGS["en"])
    for lang, strings in STRINGS.items():
        assert set(strings) == english_keys, f"{lang} is missing or has extra keys"


def test_placeholders_match_english_and_all_strings_format(auto):
    import re
    for key, english in STRINGS["en"].items():
        wanted = set(re.findall(r"{(\w+)}", english))
        for lang in SUPPORTED:
            assert set(re.findall(r"{(\w+)}", STRINGS[lang][key])) == wanted, f"{lang}.{key}"
            assert "{" not in text(lang, key, auto), f"{lang}.{key} has an unfilled placeholder"


def test_greeting_discloses_ai_in_every_language(auto):
    assert "virtual assistant" in text("en", "greeting", auto) and "AI" in text("en", "greeting", auto)
    assert "asistente virtual" in text("es", "greeting", auto) and "inteligencia artificial" in text("es", "greeting", auto)
    assert "ਵਰਚੁਅਲ ਅਸਿਸਟੈਂਟ" in text("pa", "greeting", auto) and "AI" in text("pa", "greeting", auto)
    for lang in SUPPORTED:
        assert "Feather River Auto Repair" in text(lang, "greeting", auto)


def test_business_greeting_override_replaces_english_only(auto):
    custom = auto.model_copy(update={"greeting": "Howdy from the shop! I'm the virtual assistant (AI)."})
    assert text("en", "greeting", custom).startswith("Howdy")
    assert "Howdy" not in text("es", "greeting", custom)


def test_old_language_line_is_gone(auto):
    everything = " ".join(s for lang in STRINGS.values() for s in lang.values())
    assert "Hablamos español" not in everything and "ਪੰਜਾਬੀ ਵੀ ਬੋਲਦੇ ਹਾਂ" not in everything


def test_ui_only_includes_the_businesss_languages(auto, businesses):
    full = ui_for(auto)
    assert full["order"] == ["en", "es", "pa"] and set(full["strings"]) == {"en", "es", "pa"}
    assert full["labels"] == {"en": "English", "es": "Español", "pa": "ਪੰਜਾਬੀ"}
    hvac = ui_for(businesses["sutter-buttes-hvac"])
    assert hvac["order"] == ["en", "es"] and "pa" not in hvac["strings"] and "pa" not in hvac["labels"]
    assert "(530) 555-0142" in full["strings"]["es"]["error_network"] and "1000" in full["strings"]["pa"]["error_invalid"]


def test_default_language_follows_browser_when_supported(auto, businesses):
    hvac = businesses["sutter-buttes-hvac"]
    assert default_language(auto, "es-MX,es;q=0.9,en;q=0.8") == "es"
    assert default_language(auto, "pa-IN,pa;q=0.9") == "pa"
    assert default_language(auto, "fr-FR,fr;q=0.9,pa;q=0.5") == "pa"                # first supported by preference
    assert default_language(auto, "en;q=0.5,es;q=0.9") == "es"                      # q-values respected
    assert default_language(hvac, "pa-IN,pa") == "en"                               # business doesn't offer Punjabi
    assert default_language(auto, "de,fr;q=0.8") == "en" and default_language(auto, "") == "en"
    assert default_language(auto, "es;q=abc, pa;q=0") == "en"                       # junk and q=0 are ignored


def test_business_without_english_falls_back_to_its_first_language(auto):
    spanish_only = auto.model_copy(update={"languages": ["es"]})
    assert default_language(spanish_only, "fr") == "es" and pick_language(spanish_only, "en") == "es"


def test_pick_language_rejects_unsupported(auto, businesses):
    assert pick_language(auto, "pa") == "pa" and pick_language(auto, "xx") == "en" and pick_language(auto, None) == "en"
    assert pick_language(businesses["sutter-buttes-hvac"], "pa") == "en"


def test_language_note_defaults_to_selection_but_lets_the_message_win():
    note = language_note("es", "How much is an oil change?")
    assert "latest message is written in" in note and "reply in Spanish, the language they chose" in note
    assert "Gurmukhi" not in note
    pa_note = language_note("en", "ਤੁਸੀਂ ਸ਼ਨੀਵਾਰ ਨੂੰ ਖੁੱਲ੍ਹੇ ਹੋ?")
    assert "reply in English, the language they chose" in pa_note and "Gurmukhi script" in pa_note


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
    for phrase in ("coding", "homework", "essays", "roleplay", "Never write code", "not something I can share",
                   "Things we do NOT do"):
        assert phrase in prompt


def test_speak_naturally_rule(auto):
    prompt = build_system_prompt(auto)
    assert "business file" not in prompt.lower()
    for phrase in ("We work on most domestic, Asian, and European cars", "person at the front counter",
                   "not something I can share"):
        assert phrase in prompt


def test_callback_only_when_needed_rule(auto):
    prompt = build_system_prompt(auto)
    assert "Do not end replies with an offer of a callback" in prompt
    assert "do not repeat the phone number in every reply" in prompt
    for trigger in ("(a) you can't answer", "(b) we are closed", "(c) it's an emergency", "(d) the customer asks"):
        assert trigger in prompt


def test_language_rule_covers_gurmukhi_and_the_english_note(auto):
    prompt = build_system_prompt(auto)
    assert "chose in the chat interface" in prompt and "only breaks ties" in prompt and "always wins" in prompt
    assert "Gurmukhi" in prompt and "language and script of the customer's latest message" in prompt
    assert "(always English) says nothing about the customer's language" in prompt


def test_lead_confirmation_makes_no_exact_time_promise(auto):
    prompt = build_system_prompt(auto)
    assert "Never promise an exact callback time" in prompt and "as soon as we can" in prompt


def test_not_offered_section_is_in_the_prompt(auto, businesses):
    prompt = build_system_prompt(auto)
    assert "Things we do NOT do:\n- body work and paint (dents, bumpers, collision repair)" in prompt
    assert "- diesel trucks over 10,000 lbs" in prompt and "- RVs and motorhomes" in prompt
    assert "Things we do NOT do:\n- plumbing" in build_system_prompt(businesses["sutter-buttes-hvac"])


def test_no_not_offered_section_when_the_list_is_empty(auto):
    heading = "\nThings we do NOT do:\n"      # the section heading on its own line (the rules mention it inline)
    assert heading in build_system_prompt(auto)
    assert heading not in build_system_prompt(auto.model_copy(update={"not_offered": []}))


def test_not_offered_rules(auto):
    prompt = build_system_prompt(auto)
    assert "say clearly and politely that we don't do that" in prompt
    assert "Do not offer a callback, take their name and number, or give the phone number for it" in prompt
    assert "if one of our services is a natural fit, offer help with that" in prompt
    assert "(things we don't do get a clear no, not a callback)" in prompt


def test_unknown_things_get_the_not_sure_template(auto):
    prompt = build_system_prompt(auto)
    assert 'is unknown. Begin your reply with the exact words "I\'m not sure we do"' in prompt
    assert "I'm not sure we do trailer hitches, so the team can" in prompt and "Here's what we do: brakes" in prompt


def test_the_word_listed_appears_only_in_the_avoid_line(auto, businesses):
    # The model repeats the prompt's vocabulary, so keep it to the single instruction that bans it.
    for biz in (auto, businesses["sutter-buttes-hvac"]):
        prompt = build_system_prompt(biz)
        assert prompt.lower().count("listed") == 1
        assert "Avoid the words list, listed, and listing" in prompt


def test_no_quoted_examples_of_the_bad_phrasing(auto):
    # Quoting phrases we don't want ("we don't offer it") made the model say them, so the prompt must not.
    prompt = build_system_prompt(auto)
    for bad in ("isn't something we offer", "we don't have that", "our listed services"):
        assert bad not in prompt


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
