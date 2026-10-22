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
    assert "Hablamos español" in html and "ਪੰਜਾਬੀ ਵੀ ਬੋਲਦੇ ਹਾਂ" in html and "¡Hola!" not in html
    assert 'id="close"' not in html
    assert 'id="close"' in client.get("/b/feather-river-auto?embed=1").text


def test_widget_script(make_client):
    client, _ = make_client([])
    r = client.get("/b/sutter-buttes-hvac/widget.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert "/b/sutter-buttes-hvac?embed=1" in r.text and "#0e6b5c" in r.text


def test_healthz(make_client):
    client, _ = make_client([])
    assert client.get("/healthz").json()["ok"] is True
