import json
import re
from pathlib import Path

import pytest

from tests.conftest import api_error, lead_msg, text_msg, make_message
from anthropic.types import TextBlock

URL = "/api/feather-river-auto/chat"


@pytest.fixture
def en_es_client(make_client, tmp_path):
    """Builds a client whose only business, 'en-es', offers English and Spanish but not Punjabi."""
    biz_dir = tmp_path / "en-es-biz"
    biz_dir.mkdir()
    src = (Path(__file__).parent.parent / "businesses" / "feather-river-auto.yaml").read_text()
    (biz_dir / "en-es.yaml").write_text(re.sub(r"^languages:.*$", "languages: [en, es]", src, flags=re.M))
    return lambda script: make_client(script, businesses_dir=biz_dir)


def test_chat_reply_and_logging(make_client, storage):
    client, fake = make_client([text_msg("We open at 8 AM.")])
    r = client.post(URL, json={"message": "When do you open?"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "We open at 8 AM."
    records = storage.load_records("feather-river-auto", body["conversation_id"])
    assert [x["role"] for x in records] == ["user", "assistant"]
    assert records[0]["text"] == "When do you open?" and "visitor" in records[0]
    call = fake.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] == 600
    assert "RULE 1" in call["system"]
    first_user = call["messages"][0]["content"]
    assert first_user[0]["text"] == "When do you open?"          # the customer's words come first
    assert first_user[1]["text"].startswith("[System note") and "Gurmukhi" not in first_user[1]["text"]


def test_punjabi_message_gets_a_script_hint_in_the_system_note(make_client):
    client, fake = make_client([text_msg("ਹਾਂ, ਅਸੀਂ ਸ਼ਨੀਵਾਰ ਨੂੰ ਖੁੱਲ੍ਹੇ ਹਾਂ।")])
    client.post(URL, json={"message": "ਤੁਸੀਂ ਸ਼ਨੀਵਾਰ ਨੂੰ ਖੁੱਲ੍ਹੇ ਹੋ?"})
    note = fake.calls[0]["messages"][0]["content"][1]["text"]
    assert "Punjabi" in note and "Gurmukhi script" in note


def test_model_comes_from_business_file(make_client, businesses):
    client, fake = make_client([text_msg("ok")])
    assert businesses["sutter-buttes-hvac"].model == "claude-haiku-5-5"
    client.post("/api/sutter-buttes-hvac/chat", json={"message": "hi"})
    assert fake.calls[0]["model"] == businesses["sutter-buttes-hvac"].model


def test_history_carries_over(make_client):
    client, fake = make_client([text_msg("First."), text_msg("Second.")])
    cid = client.post(URL, json={"message": "one"}).json()["conversation_id"]
    client.post(URL, json={"message": "two", "conversation_id": cid})
    msgs = fake.calls[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]


def test_lead_flow_saves_file_and_emails(make_client, storage, emailer, tmp_path):
    client, fake = make_client([lead_msg(), text_msg("Thanks Maria, we'll call tomorrow after 3.")])
    r = client.post(URL, json={"message": "My brakes squeal. Maria, 530-555-0111, tomorrow after 3"})
    body = r.json()
    assert body["lead_saved"] and "Maria" in body["reply"]
    files = list((tmp_path / "data" / "feather-river-auto" / "leads").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["name"] == "Maria Lopez" and saved["conversation_id"] == body["conversation_id"]
    assert len(emailer.sent) == 1 and emailer.sent[0][0] == "feather-river-auto"
    # tool result was sent back to the model
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and not result["is_error"]
    assert "aim to call around the time" in result["content"] and "Do not promise an exact time" in result["content"]


def test_invalid_phone_is_returned_as_tool_error(make_client, emailer):
    client, fake = make_client([lead_msg(phone="555"), text_msg("Could you double-check your number?")])
    r = client.post(URL, json={"message": "call me"})
    assert not r.json()["lead_saved"] and emailer.sent == []
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "phone" in result["content"]


def test_api_error_gives_friendly_reply(make_client, storage):
    client, _ = make_client([api_error()])
    r = client.post(URL, json={"message": "hello"})
    assert r.status_code == 200 and "(530) 555-0142" in r.json()["reply"]
    records = storage.load_records("feather-river-auto", r.json()["conversation_id"])
    assert records[-1]["error"] == "APIConnectionError"
    assert storage.load_history("feather-river-auto", r.json()["conversation_id"]) == []


def test_refusal_gives_friendly_reply(make_client):
    client, _ = make_client([text_msg("", stop_reason="refusal")])
    assert "(530) 555-0142" in client.post(URL, json={"message": "hello"}).json()["reply"]


def test_max_tokens_with_no_text_retries_once_with_more_room(make_client):
    thinking_only = make_message(stop_reason="max_tokens")
    client, fake = make_client([thinking_only, text_msg("We're open until 5:30.")])
    assert client.post(URL, json={"message": "hours?"}).json()["reply"] == "We're open until 5:30."
    assert [c["max_tokens"] for c in fake.calls] == [600, 2048]


# ---- input limits and errors --------------------------------------------
def test_message_length_limit(make_client):
    client, fake = make_client([])
    r = client.post(URL, json={"message": "x" * 1001})
    assert r.status_code == 422 and "1000" in r.json()["error"] and fake.calls == []
    assert client.post(URL, json={"message": "   "}).status_code == 422


def test_unknown_business_is_404(make_client):
    client, _ = make_client([])
    assert client.post("/api/nope/chat", json={"message": "hi"}).status_code == 404
    assert client.get("/b/nope").status_code == 404


def test_rate_limit_per_visitor_using_forwarded_for(make_client):
    client, _ = make_client([text_msg("ok")] * 6, rate_per_minute=2)
    a = {"X-Forwarded-For": "1.1.1.1, 203.0.113.7"}
    a_spoofed = {"X-Forwarded-For": "2.2.2.2, 203.0.113.7"}   # same real visitor, different fake first entry
    b = {"X-Forwarded-For": "1.1.1.1, 198.51.100.4"}          # different real visitor, same fake first entry
    assert client.post(URL, json={"message": "1"}, headers=a).status_code == 200
    assert client.post(URL, json={"message": "2"}, headers=a_spoofed).status_code == 200
    blocked = client.post(URL, json={"message": "3"}, headers={"X-Forwarded-For": "3.3.3.3, 203.0.113.7"})
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers
    assert client.post(URL, json={"message": "4"}, headers=b).status_code == 200


def test_rate_limit_without_proxy_header_uses_direct_connection(make_client):
    client, _ = make_client([text_msg("ok")] * 3, rate_per_minute=2)
    codes = [client.post(URL, json={"message": str(i)}).status_code for i in range(3)]
    assert codes == [200, 200, 429]


def test_turn_limit_stops_calling_model(make_client):
    client, fake = make_client([text_msg("ok")] * 3, max_user_turns=2)
    cid = None
    for i in range(3):
        r = client.post(URL, json={"message": f"m{i}", "conversation_id": cid}).json()
        cid = r["conversation_id"]
    assert len(fake.calls) == 2 and "(530) 555-0142" in r["reply"]


def test_conversation_id_cannot_escape_data_dir(make_client, tmp_path):
    client, _ = make_client([text_msg("ok")])
    r = client.post(URL, json={"message": "hi", "conversation_id": "../../etc/passwd"})
    assert r.status_code == 200 and r.json()["conversation_id"] != "../../etc/passwd"


# ---- no promises / on-topic: guard behavior (the model itself is covered in test_live.py) ----
def test_code_never_reaches_customer_or_history(make_client, storage):
    code = "Sure!\n```python\ndef reverse(head):\n    ...\n```"
    client, fake = make_client([text_msg(code), text_msg("ok")])
    r = client.post(URL, json={"message": "reverse a linked list in Python"}).json()
    assert "```" not in r["reply"] and "def " not in r["reply"]
    assert "Feather River Auto Repair" in r["reply"] and len(r["reply"]) < 200
    client.post(URL, json={"message": "hi", "conversation_id": r["conversation_id"]})
    assert "def reverse" not in json.dumps(fake.calls[1]["messages"])


# ---- pages ---------------------------------------------------------------
def test_chat_page_has_disclosure_and_brand(make_client):
    client, _ = make_client([])
    html = client.get("/b/feather-river-auto").text
    assert "virtual assistant" in html and "#1d3f72" in html
    assert "Hablamos español" not in html and "ਪੰਜਾਬੀ ਵੀ ਬੋਲਦੇ ਹਾਂ" not in html     # the buttons replace that line
    assert 'id="close"' not in html
    assert 'id="close"' in client.get("/b/feather-river-auto?embed=1").text


def buttons(html):
    import re
    return re.findall(r'<button type="button" class="lang" data-lang="(\w+)" lang="\w+" aria-pressed="(true|false)">([^<]+)</button>', html)


def test_language_buttons_only_for_supported_languages(make_client, en_es_client):
    client, _ = make_client([])
    assert buttons(client.get("/b/feather-river-auto").text) == [
        ("en", "true", "English"), ("es", "false", "Español"), ("pa", "false", "ਪੰਜਾਬੀ")]
    hvac = en_es_client([])[0].get("/b/en-es").text
    assert [(c, label) for c, _, label in buttons(hvac)] == [("en", "English"), ("es", "Español")]
    assert "ਪੰਜਾਬੀ" not in hvac                      # no Punjabi button and no Punjabi strings in the page


def test_buttons_are_real_buttons_in_a_labelled_group(make_client):
    html = make_client([])[0].get("/b/feather-river-auto").text
    assert '<div class="langs" id="langs" role="group" aria-label="Language">' in html
    assert html.count("aria-pressed=") == 3


def test_page_language_follows_accept_language(make_client):
    client, _ = make_client([])
    es = client.get("/b/feather-river-auto", headers={"Accept-Language": "es-MX,es;q=0.9"}).text
    assert '<html lang="es">' in es and "inteligencia artificial" in es and "Escriba su mensaje..." in es
    assert ">Enviar</button>" in es and ">Llamar</a>" in es and "Asistente virtual (IA)" in es
    assert ("es", "true", "Español") in buttons(es) and ("en", "false", "English") in buttons(es)
    pa = client.get("/b/feather-river-auto", headers={"Accept-Language": "pa-IN"}).text
    assert '<html lang="pa">' in pa and "ਆਪਣਾ ਸੁਨੇਹਾ ਲਿਖੋ..." in pa and ">ਭੇਜੋ</button>" in pa and ">ਕਾਲ ਕਰੋ</a>" in pa
    en = client.get("/b/feather-river-auto").text
    assert '<html lang="en">' in en and "Type your message..." in en and ">Send</button>" in en


def test_unsupported_browser_language_falls_back_to_english(en_es_client):
    r = en_es_client([])[0].get("/b/en-es", headers={"Accept-Language": "pa-IN,pa"})
    assert '<html lang="en">' in r.text and r.headers["vary"] == "Accept-Language"


def test_page_embeds_all_strings_for_the_script(make_client):
    import json, re
    html = make_client([])[0].get("/b/feather-river-auto").text
    found = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', html, re.S)
    assert found
    data = json.loads(found.group(1))
    assert data["order"] == ["en", "es", "pa"]
    assert "(530) 555-0142" in data["strings"]["pa"]["error_network"] and "1000" in data["strings"]["es"]["error_invalid"]


def test_single_language_business_has_no_switcher(make_client, tmp_path):
    biz_dir = tmp_path / "biz"
    biz_dir.mkdir()
    (biz_dir / "only-en.yaml").write_text(
        "name: Solo Shop\nphone: '(530) 555-0100'\nlead_email: a@b.co\nlocation: {address: x}\nhours: {mon: '9:00-17:00'}\n")
    client, _ = make_client([], businesses_dir=biz_dir)
    html = client.get("/b/only-en").text
    assert 'class="lang"' not in html and "Solo Shop&#39;s virtual assistant" in html


def test_selected_language_is_sent_to_the_model_and_logged(make_client, storage):
    client, fake = make_client([text_msg("Abrimos a las 8.")])
    r = client.post(URL, json={"message": "¿A qué hora abren?", "language": "es"}).json()
    note = fake.calls[0]["messages"][0]["content"][1]["text"]
    assert "reply in Spanish, the language they chose" in note and "latest message is written in" in note
    assert storage.load_records("feather-river-auto", r["conversation_id"])[0]["language"] == "es"


def test_english_message_under_spanish_choice_still_carries_the_rule(make_client):
    client, fake = make_client([text_msg("An oil change is estimated at...")])
    client.post(URL, json={"message": "How much is an oil change?", "language": "es"})
    note = fake.calls[0]["messages"][0]["content"][1]["text"]
    assert "Reply in the language the customer's latest message is written in" in note and "Only if the message is too short" in note


def test_missing_or_unsupported_language_defaults_to_english(en_es_client):
    client, fake = en_es_client([text_msg("ok"), text_msg("ok"), text_msg("ok")])
    client.post("/api/en-es/chat", json={"message": "hi"})
    client.post("/api/en-es/chat", json={"message": "hi", "language": "xx"})
    client.post("/api/en-es/chat", json={"message": "hi", "language": "pa"})   # this business has no Punjabi
    assert all("reply in English, the language they chose" in c["messages"][0]["content"][1]["text"] for c in fake.calls)


def test_server_messages_follow_the_chosen_language(make_client):
    # API failure
    client, _ = make_client([api_error(), api_error()])
    es = client.post(URL, json={"message": "hola", "language": "es"}).json()["reply"]
    pa = client.post(URL, json={"message": "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ", "language": "pa"}).json()["reply"]
    assert "Lo siento" in es and "(530) 555-0142" in es
    assert "ਮਾਫ਼ ਕਰਨਾ" in pa and "(530) 555-0142" in pa


def test_code_guard_reply_is_localized(make_client):
    client, _ = make_client([text_msg("```python\nprint(1)\n```")])
    reply = client.post(URL, json={"message": "write code", "language": "es"}).json()["reply"]
    assert "```" not in reply and "Solo puedo ayudar" in reply


def test_turn_limit_message_is_localized(make_client):
    client, _ = make_client([text_msg("ok")], max_user_turns=1)
    cid = client.post(URL, json={"message": "one", "language": "es"}).json()["conversation_id"]
    reply = client.post(URL, json={"message": "two", "language": "es", "conversation_id": cid}).json()["reply"]
    assert "Hemos conversado" in reply


def test_rate_limit_message_is_localized(make_client):
    client, _ = make_client([text_msg("ok")] * 3, rate_per_minute=1)
    client.post(URL, json={"message": "1", "language": "pa"})
    blocked = client.post(URL, json={"message": "2", "language": "pa"})
    assert blocked.status_code == 429 and "ਤੇਜ਼ੀ" in blocked.json()["error"]


def widget_labels(js):
    import json, re
    found = re.search(r"var labels = (\{.*?\});", js)
    assert found
    return json.loads(found.group(1))   # the script embeds them as JSON


def test_widget_label_is_available_in_each_supported_language(make_client, en_es_client):
    client, _ = make_client([])
    labels = widget_labels(client.get("/b/feather-river-auto/widget.js").text)
    assert labels == {"en": "Chat with Feather River Auto Repair", "es": "Chatear con Feather River Auto Repair",
                      "pa": "Feather River Auto Repair ਨਾਲ ਚੈਟ ਕਰੋ"}
    assert set(widget_labels(en_es_client([])[0].get("/b/en-es/widget.js").text)) == {"en", "es"}


def test_widget_script(make_client):
    client, _ = make_client([])
    r = client.get("/b/sutter-buttes-hvac/widget.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert "http://testserver/b/sutter-buttes-hvac?embed=1" in r.text and "#0e6b5c" in r.text


def test_widget_uses_configured_public_url_not_host_header(make_client):
    client, _ = make_client([], public_base_url="https://chat.example.com")
    r = client.get("/b/sutter-buttes-hvac/widget.js", headers={"Host": "evil.example.net", "X-Forwarded-Proto": "http"})
    assert "https://chat.example.com/b/sutter-buttes-hvac?embed=1" in r.text
    assert "evil.example.net" not in r.text
    assert r.headers["cache-control"] == "public, max-age=300" and r.headers["vary"] == "Host"


def test_widget_is_not_cacheable_when_url_comes_from_the_request(make_client):
    client, _ = make_client([])  # no public_base_url: dev fallback
    r = client.get("/b/sutter-buttes-hvac/widget.js", headers={"Host": "evil.example.net"})
    assert "evil.example.net" in r.text           # derived from the request...
    assert r.headers["cache-control"] == "no-store"  # ...so it must never be cached or shared


def test_public_base_url_setting_from_env(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("PUBLIC_BASE_URL", "")  # blank but set, so a real .env value can not leak in
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://myapp.onrender.com")
    assert Settings.from_env().public_base_url == "https://myapp.onrender.com"
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://chat.example.com/")
    assert Settings.from_env().public_base_url == "https://chat.example.com"


def test_healthz(make_client):
    client, _ = make_client([])
    r = client.get("/healthz")
    assert r.json() == {"ok": True}  # no client names or slugs
    assert "feather" not in r.text and "hvac" not in r.text.lower()


def test_privacy_notice_shown_in_every_language(make_client):
    from app.i18n import STRINGS
    client, _ = make_client([])
    for lang, headers in (("en", ""), ("es", "es"), ("pa", "pa")):
        html = client.get("/b/feather-river-auto", headers={"Accept-Language": headers} if headers else {}).text
        assert f'<p class="privacy" id="privacy">{STRINGS[lang]["privacy"]}</p>' in html, lang
    assert "Chats are saved so the shop can follow up with you." in STRINGS["en"]["privacy"]
    js = client.get("/static/chat.js").text
    assert "setText('privacy'" in js  # switches with the language buttons


# ---- one lead per conversation ----------------------------------------------
def _lead_files(tmp_path):
    return sorted((tmp_path / "data" / "feather-river-auto" / "leads").glob("*.json"))


def test_corrected_phone_updates_the_same_lead_and_sends_updated_email(make_client, emailer, tmp_path):
    client, _ = make_client([
        lead_msg(), text_msg("Saved."),
        lead_msg(phone="530-555-0222"), text_msg("Updated your number."),
    ])
    first = client.post(URL, json={"message": "Maria, 530-555-0111, brakes squeal, tomorrow after 3"}).json()
    r = client.post(URL, json={"message": "Sorry, my number is 530-555-0222", "conversation_id": first["conversation_id"]})
    assert r.json()["lead_saved"]
    files = _lead_files(tmp_path)
    assert len(files) == 1
    saved = json.loads(files[0].read_text())
    assert saved["phone"] == "530-555-0222" and "updated_at" in saved
    assert len(emailer.sent) == 2
    assert emailer.sent[1][3]["phone"] == "530-555-0111"  # previous values are passed along


def test_repeat_with_same_details_sends_no_second_email(make_client, emailer, tmp_path):
    client, fake = make_client([lead_msg(), text_msg("Saved."), lead_msg(), text_msg("Already have it.")])
    first = client.post(URL, json={"message": "Maria, 530-555-0111, brakes squeal, tomorrow after 3"}).json()
    client.post(URL, json={"message": "Did you get that?", "conversation_id": first["conversation_id"]})
    assert len(_lead_files(tmp_path)) == 1 and len(emailer.sent) == 1
    result = fake.calls[3]["messages"][-1]["content"][0]
    assert not result["is_error"] and "already saved" in result["content"]


def test_different_conversations_get_separate_leads(make_client, emailer, tmp_path):
    client, _ = make_client([lead_msg(), text_msg("ok"), lead_msg(), text_msg("ok")])
    client.post(URL, json={"message": "Maria, 530-555-0111, brakes, tomorrow"})
    client.post(URL, json={"message": "Maria, 530-555-0111, brakes, tomorrow"})
    assert len(_lead_files(tmp_path)) == 2 and len(emailer.sent) == 2


# ---- daily caps -----------------------------------------------------------------
def _cap_client(make_client, tmp_path, monkeypatch, biz_limit=None, global_limit=1000):
    import app.businesses as b
    real = b.load_all
    def patched(path):
        out = real(path)
        if biz_limit is not None:
            out["feather-river-auto"] = out["feather-river-auto"].model_copy(update={"daily_message_limit": biz_limit})
        return out
    monkeypatch.setattr("app.main.load_all", patched)
    return make_client([text_msg("ok")] * 10, daily_message_limit=global_limit)


def test_business_daily_cap_replies_with_phone_and_skips_claude(make_client, tmp_path, monkeypatch, caplog, auto):
    client, fake = _cap_client(make_client, tmp_path, monkeypatch, biz_limit=2)
    for _ in range(2):
        assert client.post(URL, json={"message": "hi"}).json()["reply"] == "ok"
    with caplog.at_level("WARNING"):
        r = client.post(URL, json={"message": "hi", "language": "es"})
        client.post(URL, json={"message": "hi again"})
    assert r.status_code == 200 and auto.phone in r.json()["reply"] and "Hoy" in r.json()["reply"]
    assert len(fake.calls) == 2  # Claude was not called for the capped messages
    assert sum("Daily message limit reached" in m for m in caplog.messages) == 1  # once per day


def test_global_daily_cap_spans_businesses(make_client, tmp_path, monkeypatch):
    client, fake = _cap_client(make_client, tmp_path, monkeypatch, global_limit=2)
    client.post(URL, json={"message": "hi"})
    client.post("/api/sutter-buttes-hvac/chat", json={"message": "hi"})
    r = client.post(URL, json={"message": "hi"})
    assert "call us" in r.json()["reply"] and len(fake.calls) == 2


def test_daily_cap_unit():
    from datetime import datetime, timedelta, timezone
    from app.ratelimit import DailyCap
    cap = DailyCap(global_limit=3)
    t = datetime(2026, 10, 22, 20, 0, tzinfo=timezone.utc)
    tz = "America/Los_Angeles"
    assert cap.try_acquire("a", 2, tz, t) is None and cap.try_acquire("a", 2, tz, t) is None
    assert cap.try_acquire("a", 2, tz, t) == "business"
    assert cap.try_acquire("b", 2, tz, t) is None            # takes the 3rd global slot
    assert cap.try_acquire("b", 2, tz, t) == "global"
    assert cap.first_warning("a", "business", t) and not cap.first_warning("a", "business", t)
    nxt = t + timedelta(days=1)
    assert cap.try_acquire("a", 2, tz, nxt) is None           # new day, counts start over
    assert cap.first_warning("a", "business", nxt)


def test_daily_limit_defaults_and_validation(auto):
    from app.businesses import Business
    from app.config import Settings
    import pytest
    assert auto.daily_message_limit == 300 and Settings().daily_message_limit == 1000
    with pytest.raises(Exception):
        Business.model_validate({**auto.model_dump(), "daily_message_limit": 0})


def test_lead_id_does_not_reveal_the_conversation_id(make_client, emailer):
    client, _ = make_client([lead_msg(), text_msg("ok")])
    conv = client.post(URL, json={"message": "Maria, 530-555-0111, brakes, tomorrow"}).json()["conversation_id"]
    lead_id = emailer.sent[0][2]
    assert lead_id not in conv and conv.split("-")[1] not in lead_id


# ---- difficult messages ---------------------------------------------------------
def flag_msg(category="crisis", tool_id="toolu_flag"):
    from anthropic.types import ToolUseBlock
    return make_message(ToolUseBlock(type="tool_use", id=tool_id, name="flag_conversation",
                                     input={"category": category}), stop_reason="tool_use")


def test_flagged_threat_is_logged_indexed_and_warned_without_emailing(make_client, storage, emailer, tmp_path, caplog):
    client, fake = make_client([flag_msg("threat"), text_msg("I can't help with that. If anyone is in danger, call 911.")])
    with caplog.at_level("WARNING"):
        r = client.post(URL, json={"message": "I'm going to hurt the mechanic"})
    body = r.json()
    assert body["reply"].startswith("I can't help") and not body["lead_saved"]
    assert emailer.sent == []                                            # the owner is not emailed
    assert any(t["name"] == "flag_conversation" for t in fake.calls[0]["tools"])
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and not result["is_error"]
    records = storage.load_records("feather-river-auto", body["conversation_id"])
    assert any(r.get("role") == "flag" and r.get("flag") == "threat" for r in records)
    index = (tmp_path / "data" / "feather-river-auto" / "flagged.jsonl").read_text().splitlines()
    assert len(index) == 1 and body["conversation_id"] in index[0] and '"threat"' in index[0]
    warning = [m for m in caplog.messages if "FLAGGED" in m]
    assert len(warning) == 1 and "(threat)" in warning[0] and "so far: 1" in warning[0]
    ref = json.loads(index[0])["ref"]
    assert ref in warning[0] and body["conversation_id"] not in warning[0]   # the log never has the secret id


def test_same_conversation_is_flagged_once_and_counts_conversations(make_client, tmp_path, caplog):
    client, _ = make_client([flag_msg(), text_msg("988."), flag_msg(), text_msg("988 again."),
                             flag_msg(), text_msg("988.")])
    with caplog.at_level("WARNING"):
        first = client.post(URL, json={"message": "I want to end it all"}).json()
        client.post(URL, json={"message": "still here", "conversation_id": first["conversation_id"]})
        client.post(URL, json={"message": "I want to die"})                   # a second conversation
    index = (tmp_path / "data" / "feather-river-auto" / "flagged.jsonl").read_text().splitlines()
    assert len(index) == 2
    warnings = [m for m in caplog.messages if "FLAGGED" in m]
    assert len(warnings) == 2 and "so far: 2" in warnings[1]


def test_flag_with_bad_category_is_an_error_result(make_client, tmp_path):
    client, fake = make_client([flag_msg("complaint"), text_msg("ok")])
    client.post(URL, json={"message": "hello"})
    assert fake.calls[1]["messages"][-1]["content"][0]["is_error"]
    assert not (tmp_path / "data" / "feather-river-auto" / "flagged.jsonl").exists()


def test_difficult_messages_rule_sits_right_after_the_safety_rule(auto):
    from app.prompts import build_system_prompt
    p = build_system_prompt(auto)
    assert p.index("RULE 1") < p.index("RULE 2 - DIFFICULT") < p.index("RULE 3") < p.index("ABOUT FEATHER RIVER")
    rule = p[p.index("RULE 2 - DIFFICULT"):p.index("RULE 3")]
    for needle in ("Complaint:", "988", "911", "flag_conversation", "never admit fault", "Never argue"):
        assert needle.lower() in rule.lower(), needle


# ---- homepage -------------------------------------------------------------------
def test_homepage_serves_the_landing_page(make_client):
    client, _ = make_client([])
    r = client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<title>Sutter Assist" in r.text and "Stop losing customers" in r.text
    assert "/b/feather-river-auto" in r.text                       # the demo link
    # everything else is unchanged
    assert client.get("/healthz").json() == {"ok": True}
    chat_page = client.get("/b/feather-river-auto")
    assert chat_page.status_code == 200 and "Sutter Assist" not in chat_page.text
    assert client.get("/nope").status_code == 404
