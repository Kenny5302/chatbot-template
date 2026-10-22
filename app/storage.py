"""All file storage lives here (conversation logs and leads). To move to a database later,
reimplement this class with the same methods; nothing else touches the disk."""

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
CONV_ID_RE = re.compile(r"^\d{8}-[0-9a-f]{12}$")


def valid_conversation_id(value: str | None) -> bool:
    return bool(value and CONV_ID_RE.match(value))


class FileStorage:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir)
        self._lock = threading.Lock()

    # ---- conversations -------------------------------------------------
    def new_conversation_id(self) -> str:
        return f"{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:12]}"

    def _conv_path(self, slug: str, conv_id: str) -> Path:
        if not SLUG_RE.match(slug) or not valid_conversation_id(conv_id):
            raise ValueError("invalid slug or conversation id")
        month = f"{conv_id[:4]}-{conv_id[4:6]}"
        return self.root / slug / "conversations" / month / f"{conv_id}.jsonl"

    def load_records(self, slug: str, conv_id: str) -> list[dict[str, Any]]:
        path = self._conv_path(slug, conv_id)
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def load_history(self, slug: str, conv_id: str) -> list[dict[str, Any]]:
        """API-format messages. Records without 'content' (errors, notes) are log-only."""
        return [
            {"role": r["role"], "content": r["content"]}
            for r in self.load_records(slug, conv_id)
            if "content" in r
        ]

    def append_records(self, slug: str, conv_id: str, records: list[dict[str, Any]]) -> None:
        path = self._conv_path(slug, conv_id)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = "".join(json.dumps({"ts": now, **r}, ensure_ascii=False) + "\n" for r in records)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(lines)

    def iter_conversations(self, slug: str, month: str):
        """Yield (conv_id, records) for one month ('2026-10'), for future monthly reports."""
        folder = self.root / slug / "conversations" / month
        for path in sorted(folder.glob("*.jsonl")):
            yield path.stem, self.load_records(slug, path.stem)

    # ---- leads ---------------------------------------------------------
    def save_lead(self, slug: str, lead: dict[str, Any]) -> str:
        if not SLUG_RE.match(slug):
            raise ValueError("invalid slug")
        lead_id = uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        record = {"lead_id": lead_id, "created_at": now.isoformat(timespec="seconds"), **lead}
        folder = self.root / slug / "leads"
        with self._lock:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{now:%Y-%m-%dT%H-%M-%S}_{lead_id}.json"
            path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return lead_id
