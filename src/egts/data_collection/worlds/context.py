"""Executable-world context helpers.

These helpers provide a stable world-first schema for raw episodes while the
underlying reset/snapshot implementations can still be adapter-backed,
HTTP-admin-backed, or task-specific.
"""

from __future__ import annotations

from typing import Any, Mapping


def _get(config: Any, key: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _configured_world_context(task_config: Any) -> dict[str, Any]:
    """Return user-authored world context from task config, if present."""
    configured = _get(task_config, "world_context", {}) or {}
    if isinstance(configured, Mapping):
        return dict(configured)
    return {"description": str(configured)}


def _merge_context(
    base: dict[str, Any], override: Mapping[str, Any] | None
) -> dict[str, Any]:
    merged = dict(base)
    if override:
        merged.update(dict(override))
    return merged


def build_world_context(
    *,
    task_config: Any,
    primary_server: str,
    prompt_domain: str,
    output_namespace: str,
    reset_strategy: str,
    state_strategy: str,
    reset_metadata: dict[str, Any] | None = None,
    world_context_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical executable-world context for an episode."""
    task_type = _get(task_config, "task_type", "unknown")
    required_servers = list(_get(task_config, "required_servers", []) or [])
    configured = _merge_context(
        _configured_world_context(task_config),
        world_context_override,
    )

    context = {
        "schema_version": "executable_world_v1",
        "world_id": output_namespace or primary_server,
        "task_type": task_type,
        "prompt_domain": prompt_domain,
        "output_namespace": output_namespace,
        "interface": {
            "type": "mcp",
            "primary_server": primary_server,
            "required_servers": required_servers,
        },
        "reset": {
            "operator": "rho",
            "strategy": reset_strategy,
            "metadata": reset_metadata or {},
        },
        "state": {
            "strategy": state_strategy,
        },
    }
    if configured:
        context["configured"] = configured
    return context


def build_state_evidence(diff: Any) -> dict[str, Any]:
    """Summarize post-trajectory state evidence in a world-generic schema."""
    if diff is None:
        return {
            "kind": "none",
            "changed": None,
            "summary": None,
            "total_changes": None,
        }

    changed = None
    if hasattr(diff, "is_empty") and callable(diff.is_empty):
        try:
            changed = not bool(diff.is_empty())
        except Exception:
            changed = None

    total_changes = None
    if hasattr(diff, "total_changes") and callable(diff.total_changes):
        try:
            total_changes = int(diff.total_changes())
        except Exception:
            total_changes = None
    elif changed is not None:
        total_changes = 1 if changed else 0

    summary = None
    if hasattr(diff, "get_change_summary") and callable(diff.get_change_summary):
        try:
            summary = diff.get_change_summary()
        except Exception:
            summary = str(diff)
    else:
        summary = str(diff)

    return {
        "kind": "world_diff",
        "changed": changed,
        "summary": summary,
        "total_changes": total_changes,
    }
