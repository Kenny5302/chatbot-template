import json

from tests.conftest import api_error, lead_msg, text_msg, make_message
from anthropic.types import TextBlock

URL = "/api/feather-river-auto/chat"


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


def test_language_buttons_only_for_supported_languages(make_client):
    client, _ = make_client([])
    assert buttons(client.get("/b/feather-river-auto").text) == [
        ("en", "true", "English"), ("es", "false", "Español"), ("pa", "false", "ਪੰਜਾਬੀ")]
    hvac = client.get("/b/sutter-buttes-hvac").text
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


def test_unsupported_browser_language_falls_back_to_english(make_client):
    r = make_client([])[0].get("/b/sutter-buttes-hvac", headers={"Accept-Language": "pa-IN,pa"})
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


def test_missing_or_unsupported_language_defaults_to_english(make_client):
    client, fake = make_client([text_msg("ok"), text_msg("ok"), text_msg("ok")])
    client.post(URL, json={"message": "hi"})
    client.post(URL, json={"message": "hi", "language": "xx"})
    client.post("/api/sutter-buttes-hvac/chat", json={"message": "hi", "language": "pa"})   # HVAC has no Punjabi
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


def test_widget_label_is_available_in_each_supported_language(make_client):
    client, _ = make_client([])
    labels = widget_labels(client.get("/b/feather-river-auto/widget.js").text)
    assert labels == {"en": "Chat with Feather River Auto Repair", "es": "Chatear con Feather River Auto Repair",
                      "pa": "Feather River Auto Repair ਨਾਲ ਚੈਟ ਕਰੋ"}
    assert set(widget_labels(client.get("/b/sutter-buttes-hvac/widget.js").text)) == {"en", "es"}


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
    assert client.get("/healthz").json()["ok"] is True
