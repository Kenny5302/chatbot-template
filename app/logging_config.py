"""Logging setup. Python only prints WARNING and above, without timestamps, unless something configures it,
so the app's own INFO lines (like the client-IP debug line) would never appear on Render.

Only the "app" logger (every module in this package logs under app.*) gets a handler. Uvicorn keeps its
own loggers and handlers, so its lines are not duplicated."""

import logging
import sys

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MARK = "_chatbot_handler"


def configure_logging(level: str = "INFO") -> None:
    """Send app.* logs at `level` and above to stdout with a timestamp and the logger name.
    Safe to call again: it replaces the handler it installed before instead of adding another."""
    resolved = logging.getLevelName(level.strip().upper()) if level else "INFO"
    bad_level = not isinstance(resolved, int)
    logger = logging.getLogger("app")
    for handler in [h for h in logger.handlers if getattr(h, _MARK, False)]:
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(FORMAT))
    setattr(handler, _MARK, True)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO if bad_level else resolved)
    if bad_level:
        logger.warning("Unknown LOG_LEVEL %r; using INFO", level)
