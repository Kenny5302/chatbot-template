from pathlib import Path
from typing import Any

import anthropic
import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage
from fastapi.testclient import TestClient

from app.businesses import load_all
from app.config import Settings
from app.leads import LeadService
from app.main import create_app
from app.storage import FileStorage

ROOT = Path(__file__).resolve().parent.parent


def make_message(*blocks, stop_reason: Any = "end_turn") -> Message:
    return Message(
        id="msg_test", model="claude-haiku-5-5", role="assistant", type="message",
        content=list(blocks), stop_reason=stop_reason, stop_sequence=None,
        usage=Usage(input_tokens=10, output_tokens=5),
    )


def text_msg(text: str, stop_reason: Any = "end_turn") -> Message:
    return make_message(TextBlock(type="text", text=text, citations=None), stop_reason=stop_reason)


def lead_msg(**overrides) -> Message:
    args: dict[str, object] = {"name": "Maria Lopez", "phone": "530-555-0111", "problem": "Brakes squeal",
            "best_time_to_call": "tomorrow after 3", "vehicle_or_equipment": "2015 Honda Civic", "language": "en"}
    args.update(overrides)
    return make_message(ToolUseBlock(type="tool_use", id="toolu_1", name="save_lead", input=args), stop_reason="tool_use")


class FakeClient:
    """Stands in for anthropic.Anthropic. `script` is a list of Messages or exceptions, returned in order."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeEmailer:
    configured = True

    def __init__(self):
        self.sent = []

    def send_lead(self, business, lead, lead_id):
        self.sent.append((business.slug, lead, lead_id))


@pytest.fixture
def businesses():
    return load_all(ROOT / "businesses")


@pytest.fixture
def auto(businesses):
    return businesses["feather-river-auto"]


@pytest.fixture
def storage(tmp_path):
    return FileStorage(tmp_path / "data")


@pytest.fixture
def emailer():
    return FakeEmailer()


@pytest.fixture
def make_client(tmp_path, storage, emailer):
    """Build a TestClient around a FakeClient script."""
    def build(script, **settings_kw):
        settings = Settings(anthropic_api_key="test", data_dir=tmp_path / "data", **settings_kw)
        fake = FakeClient(script)
        leads = LeadService(storage, emailer, run=lambda fn: fn())
        app = create_app(settings, client=fake, storage=storage, emailer=emailer, leads=leads)  # type: ignore[arg-type]
        return TestClient(app), fake
    return build


def api_error():
    import httpx2  # the SDK's HTTP layer
    return anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))
