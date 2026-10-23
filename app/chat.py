"""One customer message in, one reply out. Handles the Claude call and the save_lead tool loop."""

import logging
from dataclasses import dataclass
from typing import Any

import anthropic

from app.businesses import Business
from app.hours import status_line
from app.i18n import pick_language, text as ui_text
from app.leads import LeadService
from app.prompts import build_system_prompt, language_note
from app.storage import FileStorage, valid_conversation_id

log = logging.getLogger(__name__)

MAX_TOKENS = 600  # replies are a few sentences; thinking counts toward this too
RETRY_MAX_TOKENS = 2048  # one retry if thinking used up the budget before any text came out
MAX_API_CALLS = 4  # 1 reply + up to 3 tool rounds

LEAD_TOOL: dict[str, Any] = {
    "name": "save_lead",
    "description": (
        "Save a callback request for the business owner. Call it only when you have the customer's real "
        "name, phone number, a short description of the problem, and the best time to call."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Customer's name"},
            "phone": {"type": "string", "description": "Customer's phone number"},
            "problem": {"type": "string", "description": "Short description of the problem or request"},
            "best_time_to_call": {"type": "string", "description": "When the customer wants the callback"},
            "vehicle_or_equipment": {
                "type": "string",
                "description": "Vehicle (year/make/model) or equipment details, or an empty string",
            },
            "language": {"type": "string", "enum": ["en", "es", "pa"], "description": "Customer's language"},
        },
        "required": ["name", "phone", "problem", "best_time_to_call", "vehicle_or_equipment", "language"],
        "additionalProperties": False,
    },
}


FLAG_TOOL: dict[str, Any] = {
    "name": "flag_conversation",
    "description": (
        "Silently mark this conversation for the owner to review. Call it before replying when the customer "
        "threatens violence (category threat) or mentions wanting to hurt themselves (category crisis)."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {"category": {"type": "string", "enum": ["threat", "crisis"]}},
        "required": ["category"],
        "additionalProperties": False,
    },
}


@dataclass
class ChatResult:
    conversation_id: str
    reply: str
    lead_saved: bool = False


def fallback_reply(business: Business, language: str = "en") -> str:
    return ui_text(language, "reply_fallback", business)


def limit_reply(business: Business, language: str = "en") -> str:
    return ui_text(language, "reply_turn_limit", business)


def off_topic_reply(business: Business, language: str = "en") -> str:
    return ui_text(language, "reply_off_topic", business)


def guard_reply(text_: str, business: Business, language: str = "en") -> str:
    """Last line of defense: the bot never sends code, whatever the model did."""
    return off_topic_reply(business, language) if "```" in text_ else text_


def _text_of(blocks: list[dict[str, Any]]) -> str:
    return "".join(b["text"] for b in blocks if b.get("type") == "text").strip()


class ChatService:
    def __init__(self, client: anthropic.Anthropic, storage: FileStorage, leads: LeadService, max_user_turns: int = 30):
        self.client = client
        self.storage = storage
        self.leads = leads
        self.max_user_turns = max_user_turns

    def _flag(self, business: Business, conv_id: str, category: str, records: list[dict[str, Any]]) -> None:
        """Mark the conversation in its log and in data/<slug>/flagged.jsonl. Never emails anyone."""
        records.append({"role": "flag", "flag": category})
        is_new, total, ref = self.storage.add_flag(business.slug, conv_id, category)
        if is_new:
            log.warning("FLAGGED conversation (%s) for %s: ref %s (see data/%s/flagged.jsonl). Flagged conversations for %s so far: %d",
                        category, business.slug, ref, business.slug, business.slug, total)

    def handle(
        self, business: Business, message: str, conversation_id: str | None, visitor: str, language: str | None = None
    ) -> ChatResult:
        language = pick_language(business, language)
        conv_id = conversation_id if valid_conversation_id(conversation_id) else self.storage.new_conversation_id()
        assert conv_id is not None
        history = self.storage.load_history(business.slug, conv_id)
        user_turns = sum(1 for m in history if m["role"] == "user" and isinstance(m["content"][0], dict) and m["content"][0].get("type") == "text")

        if user_turns >= self.max_user_turns:
            reply = limit_reply(business, language)
            self.storage.append_records(business.slug, conv_id, [
                {"role": "user", "text": message, "visitor": visitor, "language": language},
                {"role": "assistant", "text": reply, "note": "turn limit reached"},
            ])
            return ChatResult(conv_id, reply)

        user_content = [
            {"type": "text", "text": message},
            {"type": "text", "text": status_line(business, language_hint=language_note(language, message))},
        ]
        messages = history + [{"role": "user", "content": user_content}]
        records: list[dict[str, Any]] = [
            {"role": "user", "text": message, "content": user_content, "visitor": visitor, "language": language}
        ]
        lead_saved = False
        flags: list[str] = []
        reply = ""
        max_tokens = MAX_TOKENS

        try:
            for _ in range(MAX_API_CALLS):
                resp = self.client.messages.create(
                    model=business.model,
                    max_tokens=max_tokens,
                    system=build_system_prompt(business),
                    tools=[LEAD_TOOL, FLAG_TOOL],  # type: ignore[list-item]
                    tool_choice={"type": "auto"},
                    output_config={"effort": "low"},
                    cache_control={"type": "ephemeral"},
                    messages=messages,  # type: ignore[arg-type]
                )
                blocks = [b.model_dump(mode="json", exclude_none=True) for b in resp.content]
                usage = {
                    "input_tokens": resp.usage.input_tokens,
                    "output_tokens": resp.usage.output_tokens,
                    "cache_read_input_tokens": resp.usage.cache_read_input_tokens or 0,
                    "cache_creation_input_tokens": resp.usage.cache_creation_input_tokens or 0,
                    "model": business.model,
                }

                if resp.stop_reason == "tool_use":
                    results = []
                    for b in blocks:
                        if b.get("type") != "tool_use":
                            continue
                        if b["name"] == "save_lead":
                            ok, note = self.leads.submit(business, b["input"], conv_id)
                            lead_saved = lead_saved or ok
                        elif b["name"] == "flag_conversation" and b["input"].get("category") in ("threat", "crisis"):
                            ok, note = True, "Flagged. Now write your reply to the customer, following the rules."
                            flags.append(b["input"]["category"])
                        else:
                            ok, note = False, "Unknown tool."
                        results.append({"type": "tool_result", "tool_use_id": b["id"], "content": note, "is_error": not ok})
                    messages += [{"role": "assistant", "content": blocks}, {"role": "user", "content": results}]
                    records += [
                        {"role": "assistant", "text": _text_of(blocks), "content": blocks, "usage": usage},
                        {"role": "user", "text": "", "content": results},
                    ]
                    for category in flags:
                        self._flag(business, conv_id, category, records)
                    flags = []
                    continue

                text = _text_of(blocks)
                if resp.stop_reason == "max_tokens" and not text and max_tokens < RETRY_MAX_TOKENS:
                    max_tokens = RETRY_MAX_TOKENS  # thinking ate the budget; retry once with more room
                    continue
                guarded = guard_reply(text, business, language)
                if guarded != text:
                    text, blocks = guarded, [{"type": "text", "text": guarded}]  # keep code out of history too
                if resp.stop_reason == "refusal" or not text:
                    log.warning("No usable reply (stop_reason=%s) for %s", resp.stop_reason, business.slug)
                    text = fallback_reply(business, language)
                    blocks = [{"type": "text", "text": text}]  # don't keep a refused/empty turn in history
                reply = text
                records.append({"role": "assistant", "text": text, "content": blocks, "usage": usage,
                                "stop_reason": resp.stop_reason})
                break
            else:
                reply = fallback_reply(business, language)
                records.append({"role": "assistant", "text": reply, "content": [{"type": "text", "text": reply}],
                                "note": "tool loop limit"})
        except anthropic.APIError as e:
            # Typed errors: log the kind, tell the customer something useful, keep the log consistent.
            kind = type(e).__name__
            log.error("Claude API error for %s: %s", business.slug, kind)
            self.storage.append_records(business.slug, conv_id, [
                {"role": "user", "text": message, "visitor": visitor, "language": language},
                {"role": "assistant", "text": fallback_reply(business, language), "error": kind},
            ])
            return ChatResult(conv_id, fallback_reply(business, language))

        self.storage.append_records(business.slug, conv_id, records)
        return ChatResult(conv_id, reply, lead_saved)
