"""FastAPI app: one process serves every business in businesses/."""

import logging
from pathlib import Path

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator

from app.businesses import Business, load_all
from app.chat import ChatService
from app.config import Settings
from app.emailer import GmailEmailer
from app.leads import LeadService
from app.prompts import greeting_lines
from app.ratelimit import RateLimiter, client_ip, visitor_hash
from app.storage import FileStorage

log = logging.getLogger("chatbot")
APP_DIR = Path(__file__).resolve().parent
MAX_MESSAGE_CHARS = 1000


class ChatRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_CHARS)
    conversation_id: str | None = Field(default=None, max_length=40)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty message")
        return v


def create_app(
    settings: Settings | None = None,
    client: anthropic.Anthropic | None = None,
    storage: FileStorage | None = None,
    emailer: GmailEmailer | None = None,
    leads: LeadService | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=45.0, max_retries=2)

    businesses = load_all(settings.businesses_dir)
    if not businesses:
        raise RuntimeError(f"No business files found in {settings.businesses_dir}")
    storage = storage or FileStorage(settings.data_dir)
    emailer = emailer or GmailEmailer(settings)
    leads = leads or LeadService(storage, emailer)
    chat = ChatService(client, storage, leads, settings.max_user_turns)
    limiter = RateLimiter(settings.rate_per_minute, settings.rate_per_day)
    templates = Jinja2Templates(directory=APP_DIR / "templates")

    if not emailer.configured:
        log.warning("Gmail is not configured: leads will be saved to disk but not emailed.")

    app = FastAPI(title="Business Chatbot", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

    def get_business(slug: str) -> Business:
        biz = businesses.get(slug)
        if biz is None:
            raise HTTPException(status_code=404, detail="Unknown business")
        return biz

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response  # no X-Frame-Options: the chat page is meant to be embedded in client sites

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
        return PlainTextResponse(
            "Sorry, we couldn't find that page." if exc.status_code == 404 else str(exc.detail),
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        return JSONResponse(
            {"error": f"Please send a message between 1 and {MAX_MESSAGE_CHARS} characters."}, status_code=422
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("Unhandled error on %s", request.url.path)
        return JSONResponse({"error": "Something went wrong on our end. Please try again."}, status_code=500)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "businesses": sorted(businesses)}

    @app.get("/b/{slug}", response_class=HTMLResponse)
    def chat_page(request: Request, slug: str, embed: int = 0):
        biz = get_business(slug)
        return templates.TemplateResponse(
            request, "chat.html", {"biz": biz, "greetings": greeting_lines(biz), "embed": bool(embed),
                                   "max_chars": MAX_MESSAGE_CHARS},
        )

    @app.get("/b/{slug}/widget.js")
    def widget(request: Request, slug: str):
        biz = get_business(slug)
        chat_url = str(request.url_for("chat_page", slug=slug)) + "?embed=1"
        js = templates.get_template("widget.js").render(biz=biz, chat_url=chat_url)
        return Response(js, media_type="application/javascript", headers={"Cache-Control": "public, max-age=300"})

    @app.post("/api/{slug}/chat")
    def chat_endpoint(request: Request, slug: str, body: ChatRequest):
        biz = get_business(slug)
        ip = client_ip(request, settings.trusted_proxy_hops)
        if settings.log_client_ip_debug:
            log.info("client ip debug: x-forwarded-for=%r direct=%s using=%s",
                     request.headers.get("x-forwarded-for"), request.client.host if request.client else None, ip)
        retry_after = limiter.check(f"{slug}:{ip}")
        if retry_after:
            return JSONResponse(
                {"error": f"You're sending messages quickly. Please wait a bit, or call us at {biz.phone}."},
                status_code=429, headers={"Retry-After": str(retry_after)},
            )
        result = chat.handle(biz, body.message, body.conversation_id, visitor_hash(ip, settings.visitor_hash_salt))
        return {"conversation_id": result.conversation_id, "reply": result.reply, "lead_saved": result.lead_saved}

    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Module-level `app`, built on first access, so `uvicorn app.main:app` works.

    Building it lazily (instead of `app = create_app()` at import time) keeps `import app.main` safe
    when no API key is set, e.g. when pytest imports create_app.
    """
    global _app
    if name != "app":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if _app is None:
        _app = create_app()
    return _app
