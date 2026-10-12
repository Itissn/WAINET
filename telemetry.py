"""Small allowlisted JSON events. Never pass bodies, URLs, cookies or exceptions."""
import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

LOGGER = logging.getLogger("wainet.events")
LOGGER.addHandler(logging.NullHandler())
HTTP_FIELDS = {"request_id", "method", "route", "status", "duration_ms"}
AI_FIELDS = {"operation_id", "outcome", "category", "duration_ms"}


def route_label(path):
    # Static allowlist prevents unknown URL segments/query strings leaking user data.
    try:
        path = urlsplit(path).path
    except ValueError:
        return "other"
    if path in {"/api/health", "/api/observations", "/api/auth/me", "/api/auth/login",
                "/api/auth/register", "/api/auth/logout", "/api/auth/password",
                "/api/community-status", "/api/admin/data", "/api/admin/export"}:
        return path
    if re.fullmatch(r"/api/observations/[a-f0-9-]{36}(?:/(?:image|comments|support))?", path):
        return "/api/observations/:id"
    return "other"


def emit(event, **fields):
    allowed = {"http_request": HTTP_FIELDS, "ai_analysis": AI_FIELDS}.get(event)
    if allowed is None or set(fields) != allowed:
        raise ValueError("Unknown telemetry event or fields")
    LOGGER.info(json.dumps({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), **fields},
                           separators=(",", ":")))


def configure():
    """Opt in for CLI operation; imports and test discovery remain quiet."""
    if not any(getattr(handler, "_wainet", False) for handler in LOGGER.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._wainet = True
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
