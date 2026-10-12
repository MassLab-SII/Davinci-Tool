"""Anchor-tool usage metadata for EGTS collection.

Anchor tracking is intentionally observational: collection should preserve valid
prefixes for efficiency, then downstream synthesis/export can filter by these
metadata fields when it needs anchor-targeted subsets.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Sequence


def _tool_name(call: Any) -> str:
    if isinstance(call, dict):
        return str(call.get("tool_name") or call.get("name") or "")
    return str(getattr(call, "tool_name", "") or "")


def _success(call: Any) -> bool:
    if isinstance(call, dict):
        return bool(call.get("success", True))
    return bool(getattr(call, "success", True))


def _ordered_unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _summarize_anchor_calls(
    tool_calls: Sequence[Any], anchors: set[str]
) -> dict[str, Any]:
    attempted: list[str] = []
    successful: list[str] = []
    failed: list[str] = []
    successful_calls = 0
    failed_calls = 0

    for call in tool_calls:
        name = _tool_name(call)
        if name not in anchors:
            continue
        attempted.append(name)
        if _success(call):
            successful.append(name)
            successful_calls += 1
        else:
            failed.append(name)
            failed_calls += 1

    return {
        "attempted_anchors": _ordered_unique(attempted),
        "successful_anchors": _ordered_unique(successful),
        "failed_anchors": _ordered_unique(failed),
        "successful_anchor_calls": successful_calls,
        "failed_anchor_calls": failed_calls,
    }


def _status(
    *,
    exposed_anchors: list[str],
    final_summary: dict[str, Any],
    pre_summary: dict[str, Any],
    removed_anchor_attempts: list[str],
) -> str:
    if not exposed_anchors:
        return "none_exposed"

    successful = set(final_summary["successful_anchors"])
    attempted = set(final_summary["attempted_anchors"])
    failed = set(final_summary["failed_anchors"])

    if successful and successful == set(exposed_anchors):
        return "all_used"
    if successful:
        return "partial"
    if removed_anchor_attempts:
        return "trimmed_by_valid_prefix"
    if failed or pre_summary["failed_anchors"]:
        return "failed_only"
    if attempted:
        return "failed_only"
    return "none_used"


def build_anchor_usage_metadata(
    *,
    exposed_anchors: Sequence[str],
    required_anchors: Sequence[str],
    pre_retention_tool_calls: Sequence[Any],
    final_tool_calls: Sequence[Any],
    retention_applied: bool,
) -> dict[str, Any]:
    """Build anchor usage metadata before and after valid-prefix retention.

    Args:
        exposed_anchors: Anchor-class tools visible in the episode.
        required_anchors: Anchors explicitly sampled as capability targets.
        pre_retention_tool_calls: Tool calls before pruning/valid-prefix trimming.
        final_tool_calls: Tool calls retained in the saved trajectory.
        retention_applied: Whether any retention/pruning transformation ran.

    Returns:
        JSON-serializable anchor usage metadata for filtering and analysis.
    """
    exposed = _ordered_unique(exposed_anchors)
    required = _ordered_unique(required_anchors)
    anchor_set = set(exposed) | set(required)

    pre_summary = _summarize_anchor_calls(pre_retention_tool_calls, anchor_set)
    final_summary = _summarize_anchor_calls(final_tool_calls, anchor_set)

    pre_attempted = set(pre_summary["attempted_anchors"])
    final_attempted = set(final_summary["attempted_anchors"])
    pre_successful = set(pre_summary["successful_anchors"])
    final_successful = set(final_summary["successful_anchors"])

    removed_anchor_attempts = _ordered_unique(
        name for name in exposed + required if name in pre_attempted - final_attempted
    )
    removed_successful_anchor_calls = _ordered_unique(
        name for name in exposed + required if name in pre_successful - final_successful
    )

    missing = _ordered_unique(name for name in exposed if name not in final_successful)
    status = _status(
        exposed_anchors=exposed,
        final_summary=final_summary,
        pre_summary=pre_summary,
        removed_anchor_attempts=removed_anchor_attempts,
    )

    coverage_ratio = (
        len(final_successful & set(exposed)) / len(exposed) if exposed else 0.0
    )

    return {
        "anchor_exposed": bool(exposed),
        "has_required_anchors": bool(required),
        "exposed_anchors": exposed,
        "required_anchors": required,
        "final_prefix": {
            "status": status,
            "used_anchors": _ordered_unique(
                name for name in exposed if name in final_successful
            ),
            "missing_anchors": missing,
            "attempted_anchors": final_summary["attempted_anchors"],
            "successful_anchors": final_summary["successful_anchors"],
            "failed_anchors": final_summary["failed_anchors"],
            "successful_anchor_calls": final_summary["successful_anchor_calls"],
            "failed_anchor_calls": final_summary["failed_anchor_calls"],
            "anchor_coverage_ratio": round(coverage_ratio, 4),
        },
        "pre_retention": pre_summary,
        "retention_effect": {
            "applied": bool(retention_applied),
            "removed_anchor_attempts": removed_anchor_attempts,
            "removed_successful_anchor_calls": removed_successful_anchor_calls,
            "valid_prefix_removed_anchor_attempts": bool(removed_anchor_attempts),
        },
    }
