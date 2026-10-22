from pathlib import Path

from scripts import draft_business as d
from tests.conftest import FakeClient, text_msg


def test_slug_from_url():
    assert d.slug_from_url("https://www.Joes-Auto.com/about") == "joes-auto"
    assert d.slug_from_url("https://yubacityhvac.net") == "yubacityhvac"


def test_extract_yaml_from_fenced_block():
    assert d.extract_yaml("Here you go:\n```yaml\nname: X\n```\n") == "name: X\n"


def test_example_in_prompt_is_valid():
    assert d.check(d.EXAMPLE) == []


def test_check_reports_problems():
    assert d.check("name: X\n")


def test_draft_uses_sonnet_and_returns_yaml(monkeypatch):
    class Stream:
        def __init__(self, msg):
            self.msg = msg
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get_final_message(self):
            return self.msg

    calls = []

    class FakeBeta:
        class messages:
            @staticmethod
            def stream(**kw):
                calls.append(kw)
                return Stream(text_msg("```yaml\nname: Test Shop\n```"))

    class Client:
        beta = FakeBeta

    out = d.draft(Client(), "https://x.com")  # type: ignore[arg-type]
    assert out == "name: Test Shop\n"
    assert calls[0]["model"] == "claude-sonnet-5-5"
    assert calls[0]["tools"][0]["type"] == "web_fetch_20260209"
