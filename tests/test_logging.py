import logging
import re
import smtplib

from app.config import Settings
from app.emailer import GmailEmailer
from app.logging_config import configure_logging
from tests.conftest import text_msg
from tests.test_chat_api import URL, flag_msg

STAMPED = r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} (INFO|WARNING|ERROR) app\.\w+: "


def lines_with(out: str, needle: str) -> list[str]:
    return [line for line in out.splitlines() if needle in line]


def test_important_log_lines_reach_stdout_once_with_timestamp_and_logger_name(make_client, capsys, tmp_path, auto):
    client, _ = make_client([flag_msg("threat"), text_msg("Call 911."), text_msg("unused")],
                            log_client_ip_debug=True, daily_message_limit=1)
    client.post(URL, json={"message": "I'm going to hurt someone"})       # client ip debug + FLAGGED
    client.post(URL, json={"message": "hello again"})                      # over the daily cap
    client.post(URL, json={"message": "and again"})                        # still capped: no second warning

    emailer = GmailEmailer(Settings(gmail_address="a@b.co", gmail_app_password="x", data_dir=tmp_path), sleep=lambda s: None)
    def boom(msg):
        raise smtplib.SMTPServerDisconnected("down")
    emailer._send_once = boom  # type: ignore[method-assign]
    emailer.send_lead(auto, {"name": "A", "phone": "5305550111", "problem": "p", "best_time_to_call": "now"}, "abc")

    out = capsys.readouterr().out
    for needle in ("client ip debug", "FLAGGED", "Daily message limit reached", "LEAD EMAIL NOT SENT"):
        found = lines_with(out, needle)
        assert len(found) >= 1, f"{needle!r} missing from output:\n{out}"
        assert all(re.match(STAMPED, line) for line in found), found
    assert len(lines_with(out, "FLAGGED")) == 1                            # not duplicated
    assert len(lines_with(out, "Daily message limit reached")) == 1        # once per day
    assert "app.chat" in out and "app.emailer" in out and "app.main" in out


def test_log_level_is_respected_and_bad_values_fall_back_to_info(capsys):
    configure_logging("WARNING")
    logging.getLogger("app.test").info("quiet")
    logging.getLogger("app.test").warning("loud")
    out = capsys.readouterr().out
    assert "loud" in out and "quiet" not in out

    configure_logging("nonsense")
    logging.getLogger("app.test").info("shown")
    out = capsys.readouterr().out
    assert "Unknown LOG_LEVEL" in out and "shown" in out


def test_configuring_twice_does_not_duplicate_lines(capsys):
    configure_logging("INFO")
    configure_logging("INFO")
    logging.getLogger("app.test").info("once please")
    assert capsys.readouterr().out.count("once please") == 1


def test_only_the_app_logger_is_touched_so_uvicorn_is_not_duplicated():
    configure_logging("INFO")
    assert not logging.getLogger().handlers or all(
        not getattr(h, "_chatbot_handler", False) for h in logging.getLogger().handlers)
    assert not logging.getLogger("uvicorn").handlers or all(
        not getattr(h, "_chatbot_handler", False) for h in logging.getLogger("uvicorn").handlers)


def test_log_level_setting_and_start_command(monkeypatch):
    from pathlib import Path
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert Settings.from_env().log_level == "debug"
    monkeypatch.setenv("LOG_LEVEL", "")
    assert Settings.from_env().log_level == "INFO"
    root = Path(__file__).resolve().parent.parent
    assert "--no-access-log" in (root / "render.yaml").read_text()
    assert "--no-access-log" in (root / "README.md").read_text()
