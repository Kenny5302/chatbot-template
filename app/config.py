"""Settings, read from environment variables (a .env file is loaded for local dev)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = ""
    gmail_address: str = ""
    gmail_app_password: str = ""
    operator_bcc_email: str = ""
    visitor_hash_salt: str = ""
    data_dir: Path = PROJECT_ROOT / "data"
    businesses_dir: Path = PROJECT_ROOT / "businesses"
    max_user_turns: int = 30
    rate_per_minute: int = 10
    rate_per_day: int = 60
    daily_message_limit: int = 1000  # across all businesses
    trusted_proxy_hops: int = 1
    public_base_url: str = ""
    log_client_ip_debug: bool = False
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        env = os.environ.get
        return cls(
            anthropic_api_key=env("ANTHROPIC_API_KEY", "").strip(),
            gmail_address=env("GMAIL_ADDRESS", "").strip(),
            gmail_app_password=env("GMAIL_APP_PASSWORD", "").replace(" ", ""),
            operator_bcc_email=env("OPERATOR_BCC_EMAIL", "").strip(),
            visitor_hash_salt=env("VISITOR_HASH_SALT", "").strip(),
            data_dir=Path(env("DATA_DIR", "").strip() or PROJECT_ROOT / "data"),
            public_base_url=(env("PUBLIC_BASE_URL", "").strip() or env("RENDER_EXTERNAL_URL", "").strip()).rstrip("/"),
            daily_message_limit=int(env("DAILY_MESSAGE_LIMIT", "").strip() or 1000),
            trusted_proxy_hops=int(env("TRUSTED_PROXY_HOPS", "").strip() or 1),
            log_level=env("LOG_LEVEL", "").strip() or "INFO",
            log_client_ip_debug=env("LOG_CLIENT_IP_DEBUG", "").strip() == "1",
        )
