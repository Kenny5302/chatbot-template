import json

import pytest

from app.crisis import CRISIS_PHRASES, detect_crisis
from app.i18n import STRINGS
from tests.conftest import api_error, text_msg

URL = "/api/feather-river-auto/chat"

MATCHES = [
    ("en", "I want to kill myself"), ("en", "i wanna die"), ("en", "I want to die."), ("en", "thinking about suicide"),
    ("en", "I'm going to hurt myself"), ("en", "I DON'T WANT TO LIVE ANYMORE"), ("en", "dont want to be alive"),
    ("en", "I want to end my life"), ("en", "everyone would be better off dead"), ("en", "I keep cutting myself"),
    ("es", "quiero matarme"), ("es", "Quiero morir"), ("es", "estoy pensando en el suicidio"),
    ("es", "me quiero quitar la vida, quitarme la vida"), ("es", "ya no quiero vivir"),
    ("es", "voy a hacerme daño"), ("es", "voy a hacerme dano"), ("es", "no quiero seguir viviendo"),
    ("pa", "ਮੈਂ ਮਰਨਾ ਚਾਹੁੰਦਾ ਹਾਂ"), ("pa", "ਮੈਂ ਮਰਨਾ ਚਾਹੁੰਦੀ ਹਾਂ"), ("pa", "ਮੈਂ ਖੁਦਕੁਸ਼ੀ ਕਰਨ ਬਾਰੇ ਸੋਚ ਰਿਹਾ ਹਾਂ"),
    ("pa", "ਮੈਂ ਹੁਣ ਜੀਉਣਾ ਨਹੀਂ ਚਾਹੁੰਦਾ।"), ("pa", "ਮੈਂ ਆਪਣੀ ਜਾਨ ਲੈਣ ਬਾਰੇ ਸੋਚ ਰਿਹਾ ਹਾਂ।"),
    ("pa", "ਮੈਂ ਆਪਣੇ ਆਪ ਨੂੰ ਨੁਕਸਾਨ ਪਹੁੰਚਾਵਾਂਗਾ"), ("pa", "ਮੈਂ ਆਪਣੇ ਆਪ ਨੂੰ ਮਾਰ ਲਵਾਂਗਾ"),
    ("pa", "ਖ਼ੁਦਕੁਸ਼ੀ"),  # typed with the nukta on ਖ and the composed ਸ਼
    ("en", "main khudkushi karna chahunda"), ("en", "mein marna chahunda haan"),  # Punjabi in Latin letters
]

NO_MATCH = [
    "My brakes are making a grinding noise", "How much is an oil change?", "this wait is killing me",
    "Do you work on diesel trucks?", "¿Cuánto cuesta el cambio de aceite?", "ਕੀ ਤੁਸੀਂ ਬਰੇਕ ਠੀਕ ਕਰਦੇ ਹੋ?",
    "I need a smog check, my car is dying", "Quiero cambiar mis llantas", "",
]


@pytest.mark.parametrize("lang,message", MATCHES)
def test_crisis_phrases_are_detected_with_the_right_language(lang, message):
    assert detect_crisis(message) == lang, message


@pytest.mark.parametrize("message", NO_MATCH)
def test_ordinary_messages_are_not_crisis(message):
    assert detect_crisis(message) is None, message


def test_phrase_list_is_one_reviewable_list_of_valid_languages():
    assert CRISIS_PHRASES and {lang for lang, _ in CRISIS_PHRASES} <= {"en", "es", "pa"}


def test_crisis_line_exists_in_every_language_and_names_988_and_911():
    for lang in ("en", "es", "pa"):
        line = STRINGS[lang]["crisis_line"]
        assert "988" in line and "911" in line, lang


# ---- the API-error fallback ---------------------------------------------------------
def test_api_error_with_crisis_message_gets_988_line_and_is_flagged(make_client, storage, emailer, tmp_path, caplog, auto):
    client, _ = make_client([api_error()])
    with caplog.at_level("WARNING"):
        body = client.post(URL, json={"message": "I want to kill myself"}).json()
    assert "988" in body["reply"] and "911" in body["reply"] and auto.phone in body["reply"]
    assert emailer.sent == []
    records = storage.load_records("feather-river-auto", body["conversation_id"])
    assert any(r.get("role") == "flag" and r.get("flag") == "crisis" for r in records)
    assert any(r.get("error") == "APIConnectionError" for r in records)
    index = (tmp_path / "data" / "feather-river-auto" / "flagged.jsonl").read_text().splitlines()
    assert len(index) == 1 and json.loads(index[0])["category"] == "crisis"
    assert any("FLAGGED" in m and "(crisis)" in m for m in caplog.messages)


@pytest.mark.parametrize("message,lang", [("quiero morir", "es"), ("ਮੈਂ ਮਰਨਾ ਚਾਹੁੰਦਾ ਹਾਂ", "pa"), ("I want to die", "en")])
def test_crisis_fallback_is_in_the_customers_language(make_client, message, lang):
    client, _ = make_client([api_error()])
    reply = client.post(URL, json={"message": message, "language": "en"}).json()["reply"]  # even if "English" is chosen
    assert STRINGS[lang]["crisis_line"] in reply


def test_api_error_with_ordinary_message_is_unchanged_and_not_flagged(make_client, tmp_path, auto):
    client, _ = make_client([api_error()])
    reply = client.post(URL, json={"message": "How much for brakes?"}).json()["reply"]
    assert "988" not in reply and auto.phone in reply
    assert not (tmp_path / "data" / "feather-river-auto" / "flagged.jsonl").exists()


def test_empty_model_reply_with_crisis_message_also_gets_the_line(make_client, tmp_path):
    client, _ = make_client([text_msg("")])
    reply = client.post(URL, json={"message": "suicide"}).json()["reply"]
    assert "988" in reply and (tmp_path / "data" / "feather-river-auto" / "flagged.jsonl").exists()
