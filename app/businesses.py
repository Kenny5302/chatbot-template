"""Business YAML schema and loader. One file in businesses/ = one client."""

import re
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_MODEL = "claude-haiku-5-5"


class BusinessFileError(Exception):
    pass


class _Strict(BaseModel):
    # Reject unknown keys so a typo in a YAML file fails loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid")


class Location(_Strict):
    address: str
    map_url: str | None = None


class Service(_Strict):
    name: str
    description: str = ""
    price: str = ""


class FAQ(_Strict):
    q: str
    a: str


class Brand(_Strict):
    primary: str = "#1f4e79"
    accent: str = "#f2a900"
    logo_url: str | None = None

    @field_validator("primary", "accent")
    @classmethod
    def _hex_color(cls, v: str) -> str:
        if not COLOR_RE.match(v):
            raise ValueError("must be a hex color like #1f4e79")
        return v

    @field_validator("logo_url")
    @classmethod
    def _http_url(cls, v: str | None) -> str | None:
        if v and not v.startswith(("https://", "http://")):
            raise ValueError("must start with http:// or https://")
        return v


class Business(_Strict):
    name: str
    slug: str = ""
    timezone: str = "America/Los_Angeles"
    phone: str
    lead_email: str
    location: Location
    hours: dict[str, str]
    holidays_closed: list[date] = Field(default_factory=list)
    services: list[Service] = Field(default_factory=list)
    not_offered: list[str] = Field(default_factory=list)  # things the business clearly does NOT do
    faqs: list[FAQ] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)
    languages: list[Literal["en", "es", "pa"]] = Field(default_factory=lambda: ["en"])
    brand: Brand = Field(default_factory=Brand)
    model: str = DEFAULT_MODEL
    greeting: str | None = None

    @field_validator("languages")
    @classmethod
    def _need_language(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("list at least one language")
        return v

    @field_validator("not_offered")
    @classmethod
    def _clean_not_offered(cls, v: list[str]) -> list[str]:
        items = [item.strip() for item in v]
        if any(not item for item in items):
            raise ValueError("not_offered entries can't be empty")
        return items

    @field_validator("lead_email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("not a valid email address")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v: str) -> str:
        from zoneinfo import ZoneInfo

        ZoneInfo(v)  # raises if unknown
        return v

    @field_validator("hours")
    @classmethod
    def _hours(cls, v: dict[str, str]) -> dict[str, str]:
        from app.hours import parse_ranges

        out: dict[str, str] = {}
        for day, value in v.items():
            key = day.lower()
            if key not in DAYS:
                raise ValueError(f"unknown day '{day}' (use mon..sun)")
            parse_ranges(str(value))  # raises ValueError on bad format
            out[key] = str(value)
        return out


def load_business(path: Path) -> Business:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("file must contain a YAML mapping")
        biz = Business.model_validate(raw)
    except (OSError, yaml.YAMLError, ValueError, ValidationError) as e:
        raise BusinessFileError(f"{path.name}: {e}") from e
    slug = biz.slug or path.stem
    if not SLUG_RE.match(slug):
        raise BusinessFileError(f"{path.name}: slug '{slug}' must be lowercase letters, digits, hyphens")
    return biz.model_copy(update={"slug": slug})


def load_all(directory: Path) -> dict[str, Business]:
    businesses: dict[str, Business] = {}
    for path in sorted(directory.glob("*.yaml")):
        if path.name.endswith(".draft.yaml"):
            continue
        biz = load_business(path)
        if biz.slug in businesses:
            raise BusinessFileError(f"{path.name}: duplicate slug '{biz.slug}'")
        businesses[biz.slug] = biz
    return businesses
