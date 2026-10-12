"""Pre-synthesis quality gate helpers for trajectory tool-call quality."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def build_tool_quality_stats(ordered_tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build quality stats from normalized ordered tool-call sequence."""
    total_calls = 0
    failed_calls = 0
    per_tool: Dict[str, Dict[str, int]] = {}

    for tc in ordered_tool_calls:
        if not isinstance(tc, dict):
            continue
        total_calls += 1

        tool_name = str(tc.get("tool_name") or "unknown")
        stats = per_tool.setdefault(tool_name, {"success": 0, "failed": 0})

        if bool(tc.get("success", True)):
            stats["success"] += 1
        else:
            stats["failed"] += 1
            failed_calls += 1

    failure_rate = (failed_calls / total_calls) if total_calls > 0 else 0.0
    failure_only_tools = sorted(
        [
            tool_name
            for tool_name, stats in per_tool.items()
            if int(stats.get("failed", 0)) > 0 and int(stats.get("success", 0)) == 0
        ]
    )

    return {
        "total_calls": int(total_calls),
        "failed_calls": int(failed_calls),
        "failure_rate": float(failure_rate),
        "per_tool": per_tool,
        "failure_only_tools": failure_only_tools,
    }


def evaluate_tool_quality(
    ordered_tool_calls: List[Dict[str, Any]],
    *,
    reject_failure_only_tools: bool,
    max_tool_failure_rate: float,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Evaluate whether trajectory should be skipped before synthesis."""
    stats = build_tool_quality_stats(ordered_tool_calls)
    reasons: List[str] = []

    failure_only_tools = stats.get("failure_only_tools", [])
    if reject_failure_only_tools and failure_only_tools:
        reasons.append(
            "failure-only tools detected: "
            + ", ".join(str(name) for name in failure_only_tools)
        )

    total_calls = int(stats.get("total_calls", 0) or 0)
    failed_calls = int(stats.get("failed_calls", 0) or 0)
    failure_rate = float(stats.get("failure_rate", 0.0) or 0.0)
    if total_calls > 0 and failure_rate > max_tool_failure_rate:
        reasons.append(
            "failure rate too high: "
            f"{failed_calls}/{total_calls}={failure_rate:.2%} > {max_tool_failure_rate:.2%}"
        )

    if reasons:
        return False, "; ".join(reasons), stats
    return True, "tool quality gate passed", stats

