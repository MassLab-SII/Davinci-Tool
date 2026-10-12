"""Helpers for stable executable-world session headers."""

from __future__ import annotations

from typing import Mapping


WORLD_SESSION_HEADER = "X-World-Session"


def build_world_session_id(run_id: str, worker_id: int) -> str:
    """Build a stable hidden world-session id for one worker."""
    return f"{run_id}-worker-{worker_id}"


def build_world_session_headers(
    base_headers: Mapping[str, str] | None,
    *,
    run_id: str,
    worker_id: int,
) -> dict[str, str]:
    """Merge the worker session header into existing HTTP headers."""
    headers = dict(base_headers or {})
    headers[WORLD_SESSION_HEADER] = build_world_session_id(run_id, worker_id)
    return headers
