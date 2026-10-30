"""Minimal logging configuration.

Uses the standard library so no extra dependency is required. Log records are
emitted as ``logger=... event=... key=value`` lines; structured fields are passed
through ``extra``. Callers must never pass secrets, tokens, or Authorization
headers as fields.
"""

import logging

from app.core.config import Settings

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


class KeyValueFormatter(logging.Formatter):
    """Append ``extra`` fields as key=value pairs after the message."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED and not key.startswith("_")
        }
        if not fields:
            return base
        rendered = " ".join(f"{key}={value!r}" for key, value in sorted(fields.items()))
        return f"{base} {rendered}"


def configure_logging(settings: Settings) -> None:
    """Configure the root logger once; safe to call repeatedly."""
    root = logging.getLogger()
    if getattr(root, "_rescuepay_configured", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        KeyValueFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())
    root._rescuepay_configured = True  # type: ignore[attr-defined]
