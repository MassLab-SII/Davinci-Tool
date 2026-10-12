"""Replay synthesis utilities for task-oriented collection artifacts."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from data_collection.problem_synthesizer import TaskType

logger = logging.getLogger(__name__)


def _safe_json_dumps(obj: Any, *, ensure_ascii: bool = False) -> str:
    """Safe json.dumps that handles non-serializable types by converting to str."""
    try:
        return json.dumps(obj, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError):
        if isinstance(obj, dict):
            safe = {str(k): _safe_json_value(v) for k, v in obj.items()}
            return json.dumps(safe, ensure_ascii=ensure_ascii)
        return json.dumps(str(obj), ensure_ascii=ensure_ascii)


def _safe_json_value(val: Any) -> Any:
    """Recursively convert a value to a JSON-serializable form."""
    if val is None or isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, (list, tuple)):
        return [_safe_json_value(v) for v in val]
    if isinstance(val, dict):
        return {str(k): _safe_json_value(v) for k, v in val.items()}
    return str(val)


_MUTATION_KEYWORDS = (
    "set_",
    "write",
    "create",
    "delete",
    "remove",
    "update",
    "modify",
    "move",
    "edit",
    "add",
    "insert",
    "send_",
    "post_",
    "put_",
    "cancel",
    "archive",
    "revoke",
)

_STATUS_TO_SET_TOOL = {
    "wifi_status": "set_wifi_status",
    "bluetooth_status": "set_bluetooth_status",
    "cellular_status": "set_cellular_status",
    "location_service_status": "set_location_service_status",
    "low_battery_mode_status": "set_low_battery_mode_status",
}


@dataclass
class ReplaySynthesisConfig:
    enabled: bool = False
    max_problem_candidates: int = 3
    max_replay_attempts: int = 2
    min_quality_tier: str = "acceptable"
    tool_sequence_selection: str = "heuristic"
    verify_final_state: bool = True
    save_failed_replays: bool = True
    max_selected_tool_calls: int = 12
    max_selected_mutations: int = 10
    harness_mode: str = "full"
    harness_max_retries_per_step: int = 2
    harness_model: str = "trajectory_collection"
    harness_fallback_threshold: float = 0.5
    preserve_failure_recovery_chains: bool = True
    dependency_relevance_filter: bool = True
    llm_problem_synthesis: bool = True
    max_dependency_distance: int = 5
    polish_enabled: bool = True
    polish_model: str = "judge_model"
    enable_quality_judge: bool = True
    judge_hard_weight: float = 0.70
    judge_soft_weight: float = 0.20
    judge_dual_bonus: float = 0.10
    judge_threshold_high: float = 0.85
    judge_threshold_acceptable: float = 0.70
    min_original_tool_calls: int = 3
    min_selected_tool_calls: int = 2
    tool_name_noise_extra: Optional[List[str]] = None
    tool_name_noise_exclude: Optional[List[str]] = None


@dataclass
class ToolSequenceSelection:
    selected_calls: List[Dict[str, Any]] = field(default_factory=list)
    dropped_calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReplayProblemSpec:
    problem: str
    task_type: str
    evidence_summary: str
    expected_outcome: Dict[str, Any] = field(default_factory=dict)
    required_tools_hint: List[str] = field(default_factory=list)
    judge: Dict[str, Any] = field(default_factory=dict)
    reference_answer: str = ""


@dataclass
class ReplaySynthesisResult:
    accepted: bool
    problem_spec: Optional[ReplayProblemSpec] = None
    selection: Optional[ToolSequenceSelection] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[str] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)
    review_record: Optional[Dict[str, Any]] = None
    rejected_reason: str = ""
    artifact_dir: Optional[str] = None


class ToolSequenceSelector:
    def select(
        self,
        tool_calls: Iterable[Any],
        task_type: str,
        *,
        max_selected: int = 12,
        max_selected_mutations: int = 10,
        max_dependency_distance: int = 5,
        preserve_failure_recovery_chains: bool = True,
        dependency_relevance_filter: bool = True,
        verification_window: int = 3,
    ) -> ToolSequenceSelection:
        normalized = [self._normalize_call(call, idx + 1) for idx, call in enumerate(tool_calls)]
        successful_indices = [idx for idx, call in enumerate(normalized) if call.get("success", True)]
        if not successful_indices:
            return ToolSequenceSelection(
                dropped_calls=[self._drop(call, "failed_or_empty") for call in normalized]
            )

        selected_indices: set[int] = set()

        if str(task_type).lower() == TaskType.MUTATION.value:
            self._select_mutation_chain(
                normalized, successful_indices, selected_indices,
                max_dependency_distance=max_dependency_distance,
                max_mutations=max_selected_mutations,
                dependency_relevance_filter=dependency_relevance_filter,
                verification_window=verification_window,
            )
        else:
            self._select_retrieval_chain(
                normalized, successful_indices, selected_indices,
                max_selected=max_selected,
            )

        if preserve_failure_recovery_chains:
            selected_indices.update(
                self._find_recoverable_failures(normalized, selected_indices)
            )

        selected, dropped = self._build_selected_and_dropped(
            normalized, selected_indices, task_type,
        )

        if len(selected) > max_selected:
            selected, overflow = self._truncate_selected(selected, max_selected)
            dropped.extend(self._drop(call, "over_max_selected_tool_calls") for call in overflow)

        for new_step, call in enumerate(selected, start=1):
            call["step"] = new_step
        return ToolSequenceSelection(selected_calls=selected, dropped_calls=dropped)

    # ── chain-based selection helpers ────────────────────────────────

    @staticmethod
    def _select_mutation_chain(
        calls: List[Dict[str, Any]],
        successful_indices: List[int],
        selected_indices: set[int],
        *,
        max_dependency_distance: int = 5,
        max_mutations: int = 10,
        dependency_relevance_filter: bool = True,
        verification_window: int = 3,
    ) -> None:
        """Select all mutations + their dependency chains + verification calls."""
        mutation_indices = [
            idx for idx in successful_indices
            if _is_mutation_tool(calls[idx].get("tool_name", ""))
        ]
        if not mutation_indices:
            selected_indices.add(successful_indices[-1])
            return

        # Limit to max_mutations, preferring later ones (more likely task-completing)
        if len(mutation_indices) > max_mutations:
            mutation_indices = mutation_indices[-max_mutations:]

        for mut_idx in mutation_indices:
            selected_indices.add(mut_idx)
            # Find dependency chain for this mutation
            dep_indices = ToolSequenceSelector._find_dependency_chain(
                calls, mut_idx,
                max_distance=max_dependency_distance,
                relevance_filter=dependency_relevance_filter,
            )
            selected_indices.update(dep_indices)
            # Find verification calls after this mutation
            verif_indices = ToolSequenceSelector._find_verification_calls(
                calls, mut_idx, window=verification_window,
            )
            selected_indices.update(verif_indices)

    @staticmethod
    def _find_dependency_chain(
        calls: List[Dict[str, Any]],
        mutation_idx: int,
        *,
        max_distance: int = 5,
        relevance_filter: bool = True,
    ) -> List[int]:
        """Find the chain of retrieval calls that a mutation depends on.

        Walks backward from the mutation, collecting all retrieval calls
        that contribute context (keyword overlap, tool family relationship).
        Returns a list of indices in original order.
        """
        if mutation_idx < 1:
            return []

        mutation = calls[mutation_idx]
        mutation_target = _extract_query_from_call(mutation) or mutation.get("tool_name", "")

        start = max(0, mutation_idx - max_distance)
        chain_indices: List[int] = []

        for idx in range(mutation_idx - 1, start - 1, -1):
            tool = calls[idx].get("tool_name", "")
            if _is_mutation_tool(tool):
                continue

            if not relevance_filter:
                # Legacy: take any retrieval before the mutation
                chain_indices.append(idx)
                continue

            args_focus = _focus(calls[idx].get("arguments", {}))
            call_query = _extract_query_from_call(calls[idx])
            result_text = str(calls[idx].get("result", "") or "")[:500]
            combined = f"{args_focus} {call_query} {result_text}".lower()

            # Score relevance to mutation target
            score = 0
            if any(marker in tool for marker in ("search", "read", "lookup", "find")):
                if mutation_target and _keyword_overlap(mutation_target, combined):
                    score = 3
                elif _has_meaningful_focus(args_focus, call_query):
                    score = 1
            elif _has_meaningful_focus(args_focus, call_query):
                if mutation_target and _keyword_overlap(mutation_target, combined):
                    score = 2
                else:
                    score = 0

            if score > 0:
                chain_indices.append(idx)

        # Return in original order (reversed from backward walk)
        chain_indices.reverse()
        return chain_indices

    @staticmethod
    def _find_verification_calls(
        calls: List[Dict[str, Any]],
        mutation_idx: int,
        *,
        window: int = 3,
    ) -> List[int]:
        """Detect post-mutation verification calls (get_/list_/search_ on same target).

        After a mutation, agents often verify the change took effect. These
        verification calls are valuable training data — they teach the model
        to confirm state changes.
        """
        mutation = calls[mutation_idx]
        mutation_tool = mutation.get("tool_name", "")
        mutation_target = _extract_query_from_call(mutation)
        mutation_focus = _focus(mutation.get("arguments", {}))

        verification_indices: List[int] = []
        end = min(len(calls), mutation_idx + 1 + window)

        for idx in range(mutation_idx + 1, end):
            call = calls[idx]
            tool = call.get("tool_name", "")
            if not call.get("success", True):
                continue
            if _is_mutation_tool(tool):
                # Stop at the next mutation — verification calls come before it
                break

            # Check if this is a get/list/search on the same target
            if any(tool.startswith(p) for p in ("get_", "list_", "search_", "read_")):
                call_query = _extract_query_from_call(call)
                call_focus = _focus(call.get("arguments", {}))
                if mutation_target and call_query and _keyword_overlap(mutation_target, call_query):
                    verification_indices.append(idx)
                elif mutation_focus and call_focus and _keyword_overlap(mutation_focus, call_focus):
                    verification_indices.append(idx)
                elif _tool_family(tool) == _tool_family(mutation_tool):
                    # Same family: get_wifi_status after set_wifi_status
                    verification_indices.append(idx)

        return verification_indices

    @staticmethod
    def _select_retrieval_chain(
        calls: List[Dict[str, Any]],
        successful_indices: List[int],
        selected_indices: set[int],
        *,
        max_selected: int = 12,
    ) -> None:
        """Select a coherent retrieval chain, not just the single longest result.

        Walks backward from the terminal retrieval call, adding calls whose
        outputs or arguments relate to later selected calls.
        """
        # Find terminal: last successful non-mutation call
        terminal_idx = None
        for idx in reversed(successful_indices):
            if not _is_mutation_tool(calls[idx].get("tool_name", "")):
                terminal_idx = idx
                break

        if terminal_idx is None:
            terminal_idx = successful_indices[-1]

        selected_indices.add(terminal_idx)

        # Walk backward from terminal, collecting related calls
        for idx in range(terminal_idx - 1, -1, -1):
            if len(selected_indices) >= max_selected:
                break
            tool = calls[idx].get("tool_name", "")
            if not calls[idx].get("success", True) or _is_mutation_tool(tool):
                continue

            # Check if this call's output relates to any already-selected call
            call_query = _extract_query_from_call(calls[idx])
            call_result = str(calls[idx].get("result", "") or "")[:300]
            call_combined = f"{call_query} {call_result}".lower()

            related = False
            for sel_idx in selected_indices:
                sel_query = _extract_query_from_call(calls[sel_idx])
                sel_combined = f"{sel_query} {str(calls[sel_idx].get('result', '') or '')[:300]}".lower()
                if _keyword_overlap(call_combined, sel_combined):
                    related = True
                    break
                # Also check argument overlap between this call and selected call
                if _keyword_overlap(
                    _focus(calls[idx].get("arguments", {})),
                    _focus(calls[sel_idx].get("arguments", {})),
                ):
                    related = True
                    break

            if related:
                selected_indices.add(idx)

    @staticmethod
    def _build_selected_and_dropped(
        calls: List[Dict[str, Any]],
        selected_indices: set[int],
        task_type: str,
    ) -> tuple:
        """Build ordered selected and dropped lists from raw indices.

        When duplicate (tool_name, args_focus) pairs are both selected and
        neither is a mutation, keeps the one closer to the nearest downstream
        mutation (the other is dropped with reason 'duplicate_selected_retrieval').
        """
        selected: List[Dict[str, Any]] = []
        dropped: List[Dict[str, Any]] = []
        # Track (tool_name, focus) → idx_in_selected_list and call index
        seen_pairs: dict[tuple[str, str], tuple[int, int]] = {}
        selected_mutation_indices = {
            idx for idx in selected_indices
            if _is_mutation_tool(calls[idx].get("tool_name", ""))
        }

        def _nearest_downstream_mutation(call_idx: int) -> int:
            """Distance to nearest mutation AFTER this call, or large sentinel."""
            best = 999999
            for m_idx in selected_mutation_indices:
                if m_idx > call_idx:
                    best = min(best, m_idx - call_idx)
            return best

        for idx, call in enumerate(calls):
            pair = (call.get("tool_name", ""), _focus(call.get("arguments", {})))
            if idx in selected_indices:
                # Filter out calls with exploration artifacts even if selected
                if _has_exploration_artifacts(call.get("arguments", {})):
                    dropped.append(ToolSequenceSelector._drop(call, "exploration_artifact"))
                    continue
                is_mut = _is_mutation_tool(call.get("tool_name", ""))
                if call.get("success", True) and pair in seen_pairs and not is_mut:
                    old_pos, old_idx = seen_pairs[pair]
                    # Keep the call closer to a downstream mutation
                    old_dist = _nearest_downstream_mutation(old_idx)
                    new_dist = _nearest_downstream_mutation(idx)
                    if new_dist < old_dist:
                        # Swap: drop the old one, keep the new one
                        old_call = selected[old_pos]
                        dropped.append(ToolSequenceSelector._drop(
                            old_call, "duplicate_selected_retrieval",
                        ))
                        selected[old_pos] = None  # placeholder, will be cleaned up
                        # Build and insert the new call
                        row = dict(call)
                        row["selection_reason"] = ToolSequenceSelector._selection_reason(
                            call, task_type, calls, idx, selected_indices,
                        )
                        selected[old_pos] = row
                        seen_pairs[pair] = (old_pos, idx)
                        continue
                    else:
                        dropped.append(ToolSequenceSelector._drop(call, "duplicate_selected_retrieval"))
                        continue
                row = dict(call)
                row["selection_reason"] = ToolSequenceSelector._selection_reason(
                    call, task_type, calls, idx, selected_indices,
                )
                pos = len(selected)
                selected.append(row)
                seen_pairs[pair] = (pos, idx)
            else:
                reason = "unrelated_exploration"
                if not call.get("success", True):
                    reason = "uncorrected_or_unrelated_failure"
                elif _has_exploration_artifacts(call.get("arguments", {})):
                    reason = "exploration_artifact"
                elif pair in seen_pairs:
                    reason = "duplicate_or_repeated_exploration"
                dropped.append(ToolSequenceSelector._drop(call, reason))
                if pair not in seen_pairs:
                    seen_pairs[pair] = (-1, -1)  # marker: seen but not in selected

        # Remove any None placeholders from swaps
        selected = [s for s in selected if s is not None]

        return selected, dropped

    @staticmethod
    def _truncate_selected(
        selected: List[Dict[str, Any]],
        max_count: int,
    ) -> tuple:
        """Smart truncation: keep head (first N/3) + tail (last 2N/3) to preserve
        initial orientation and terminal execution while dropping middle fluff."""
        if len(selected) <= max_count:
            return selected, []

        head_count = max(1, max_count // 3)
        tail_count = max_count - head_count
        kept = selected[:head_count] + selected[-(tail_count):]
        overflow = selected[head_count:-(tail_count)] if tail_count < len(selected) - head_count else []
        return kept, overflow

    @staticmethod
    def _normalize_call(call: Any, source_step: int) -> Dict[str, Any]:
        if isinstance(call, dict):
            return {
                "source_step": int(call.get("source_step") or call.get("step") or source_step),
                "step": source_step,
                "tool_name": str(call.get("tool_name") or call.get("tool") or ""),
                "arguments": call.get("arguments") or {},
                "result": call.get("result", ""),
                "success": bool(call.get("success", True)),
                "error_message": call.get("error_message"),
            }
        return {
            "source_step": source_step,
            "step": source_step,
            "tool_name": str(getattr(call, "tool_name", "")),
            "arguments": getattr(call, "arguments", {}) or {},
            "result": getattr(call, "result", ""),
            "success": bool(getattr(call, "success", True)),
            "error_message": getattr(call, "error_message", None),
        }

    @staticmethod
    def _drop(call: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "source_step": call.get("source_step"),
            "tool_name": call.get("tool_name"),
            "drop_reason": reason,
        }

    @staticmethod
    def _find_dependency_before(calls: List[Dict[str, Any]], before_idx: int) -> Optional[int]:
        """Legacy dependency finder: first retrieval call before mutation (no relevance filter)."""
        for idx in range(0, before_idx):
            tool = calls[idx].get("tool_name", "")
            if _is_mutation_tool(tool):
                continue
            if any(marker in tool for marker in ("search", "read", "lookup", "find")) and _focus(calls[idx].get("arguments", {})):
                return idx
        for idx in range(0, before_idx):
            tool = calls[idx].get("tool_name", "")
            if _is_mutation_tool(tool):
                continue
            if _focus(calls[idx].get("arguments", {})) or calls[idx].get("result"):
                return idx
        for idx in range(0, before_idx):
            tool = calls[idx].get("tool_name", "")
            if not _is_mutation_tool(tool):
                return idx
        return None

    @staticmethod
    def _find_relevant_dependency(
        calls: List[Dict[str, Any]], before_idx: int, *, max_distance: int = 5,
    ) -> Optional[int]:
        """Find the most relevant retrieval call before a mutation, scoring by keyword overlap.

        Filters out unrelated dependency calls (e.g., search_reminder before set_wifi_status).
        Returns None when no call has meaningful relevance to the mutation target.
        """
        if before_idx < 1:
            return None

        mutation = calls[before_idx]
        mutation_tool = mutation.get("tool_name", "")
        mutation_args = mutation.get("arguments", {}) if isinstance(mutation.get("arguments"), dict) else {}
        mutation_target = _extract_query_from_call(mutation) or mutation_tool

        start = max(0, before_idx - max_distance)
        candidates = []

        for idx in range(before_idx - 1, start - 1, -1):
            tool = calls[idx].get("tool_name", "")
            if _is_mutation_tool(tool):
                continue

            args_focus = _focus(calls[idx].get("arguments", {}))
            call_query = _extract_query_from_call(calls[idx])
            result_text = str(calls[idx].get("result", "") or "")[:500]
            combined = f"{args_focus} {call_query} {result_text}".lower()
            has_focus = _has_meaningful_focus(args_focus, call_query)

            score = 0
            if any(marker in tool for marker in ("search", "read", "lookup", "find")):
                if mutation_target and _keyword_overlap(mutation_target, combined):
                    score = 3
                elif has_focus:
                    score = 1
            elif has_focus:
                if mutation_target and _keyword_overlap(mutation_target, combined):
                    score = 2
                else:
                    score = 0
            else:
                score = 0

            if score > 0:
                candidates.append((score, idx))

        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            return candidates[0][1]

        return None

    @staticmethod
    def _find_best_retrieval_evidence(calls: List[Dict[str, Any]]) -> int:
        best_idx = 0
        best_len = -1
        for idx, call in enumerate(calls):
            if not call.get("success", True) or _is_mutation_tool(call.get("tool_name", "")):
                continue
            result_len = len(str(call.get("result", "") or ""))
            if result_len > best_len:
                best_idx = idx
                best_len = result_len
        return best_idx

    @staticmethod
    def _find_recoverable_failures(
        calls: List[Dict[str, Any]], selected_indices: set[int]
    ) -> set[int]:
        recoverable: set[int] = set()
        for idx, call in enumerate(calls):
            if call.get("success", True) or not _has_useful_failure_feedback(call):
                continue
            later_success = ToolSequenceSelector._find_later_correcting_success(calls, idx, selected_indices)
            if later_success is not None:
                recoverable.add(idx)
                recoverable.add(later_success)
        return recoverable

    @staticmethod
    def _find_later_correcting_success(
        calls: List[Dict[str, Any]], failed_idx: int, selected_indices: set[int]
    ) -> Optional[int]:
        """Find the next successful call that corrects/compensates for a failure.

        Supports cross-family strategy adjustment:
        - Same-family correction (e.g., search_contacts("Alic") -> search_contacts("Alice"))
        - Cross-family keyword overlap (e.g., search_messages("John") fails -> search_contacts("John") succeeds)
        """
        failed = calls[failed_idx]
        failed_tool = failed.get("tool_name", "")
        failed_family = _tool_family(failed_tool)
        failed_query = _extract_query_from_call(failed)
        failed_focus = _focus(failed.get("arguments", {}))

        for idx in range(failed_idx + 1, len(calls)):
            candidate = calls[idx]
            if not candidate.get("success", True):
                continue

            cand_tool = candidate.get("tool_name", "")

            # Same-family: strong signal (e.g., search retry with corrected params)
            if _tool_family(cand_tool) == failed_family:
                if _focus(candidate.get("arguments", {})) != failed_focus:
                    return idx

            # Cross-family: keyword overlap in query/arguments
            cand_query = _extract_query_from_call(candidate)
            cand_focus = _focus(candidate.get("arguments", {}))
            if failed_query and cand_query and _keyword_overlap(failed_query, cand_query):
                return idx
            if failed_focus and cand_focus and _keyword_overlap(failed_focus, cand_focus):
                return idx

        return None

    @staticmethod
    def _selection_reason(
        call: Dict[str, Any],
        task_type: str,
        calls: Optional[List[Dict[str, Any]]] = None,
        idx: Optional[int] = None,
        selected_indices: Optional[set[int]] = None,
    ) -> str:
        if not call.get("success", True):
            return "recoverable_failure_corrected_by_later_success"
        if str(task_type).lower() == TaskType.MUTATION.value:
            if _is_mutation_tool(call.get("tool_name", "")):
                return "successful_mutation_call"
            return "dependency_for_mutation_call"
        return "retrieval_evidence_call"


# ═══════════════════════════════════════════════════════════════════════════════
# Universal Tool Selector — data-flow-based dependency detection
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class _SemanticCall:
    """Internal representation of a tool call with extracted semantic tokens."""
    idx: int
    source_step: int
    tool_name: str
    arguments: Dict[str, Any]
    result_text: str
    success: bool
    error_message: Optional[str]
    arg_tokens: "set[str]"
    result_tokens: "set[str]"
    is_mutation: bool


def _collect_leaf_strings(obj: Any, max_depth: int = 6, path_prefix: Optional[tuple] = None) -> "set[str]":
    """Recursively collect all leaf string values from nested JSON structures."""
    tokens: set[str] = set()
    if max_depth <= 0:
        return tokens
    if obj is None or isinstance(obj, (bool, int, float)):
        return tokens
    if isinstance(obj, str):
        return _tokenize_string(obj, path_prefix)
    if isinstance(obj, dict):
        for v in obj.values():
            tokens.update(_collect_leaf_strings(v, max_depth - 1, path_prefix))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            tokens.update(_collect_leaf_strings(v, max_depth - 1, path_prefix))
    return tokens


# ── path prefix normalization (dense-graph worlds) ─────────────────────

# URL schemes to skip when collecting path candidates — these are not
# filesystem paths and their components are not meaningful workspace roots.
_URL_SCHEMES: frozenset[str] = frozenset({"http", "https", "ftp", "sftp", "ws", "wss"})


def _detect_path_prefix(raw_calls: "list[Dict[str, Any]]") -> Optional[tuple]:
    """Detect the longest common path prefix across path-like argument values.

    Only scans **arguments** (not raw result text) — argument values are always
    clean, while result text often contains JSON-escaped or code-embedded paths
    with broken first components.

    Splits each path on '/' into components, strips quoting artefacts, then
    finds the longest prefix shared by at least 3 paths that span at least 2
    distinct subdirectories below the prefix.

    Returns a tuple of path components, or None when no meaningful common
    prefix exists (e.g. tool_sandbox worlds with no file paths).
    """
    path_strings: list[str] = []
    for call in raw_calls:
        args = call.get("arguments", {}) or {}
        for k, v in args.items():
            # Skip content/file-body values — they are code/text, not paths.
            # These are typically multi-KB strings with embedded URLs/comments
            # that happen to contain '/', not actual filesystem paths.
            if isinstance(k, str) and k.lower() in ("content", "text", "body", "message",
                                                     "description", "old_text", "new_text"):
                continue
            if isinstance(v, str) and "/" in v:
                low = v.strip().lower()
                # Skip very long strings (>500 chars) — these are content, not paths
                if len(low) > 500:
                    continue
                if any(low.startswith(s + "://") or low.startswith(s + "s://")
                       for s in _URL_SCHEMES):
                    continue
                if any(c in low for c in '*?['):
                    continue
                path_strings.append(low)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and "/" in item:
                        low = item.strip().lower()
                        if len(low) > 500:
                            continue
                        if not any(low.startswith(s + "://") for s in _URL_SCHEMES):
                            if not any(c in low for c in '*?['):
                                path_strings.append(low)

    if len(path_strings) < 3:
        return None

    # Split into components, normalizing away JSON-escaping artefacts
    components_list: list[list[str]] = []
    for p in path_strings:
        comps = [c.strip('"\'\\ ') for c in p.split("/")
                 if c.strip('"\'\\ ') and c.strip('"\'\\ ') not in (".", "..")]
        if comps:
            components_list.append(comps)

    if len(components_list) < 3:
        return None

    # Find longest common component-level prefix
    min_len = min(len(c) for c in components_list)
    common: list[str] = []
    for i in range(min_len):
        comp = components_list[0][i]
        if all(c[i] == comp for c in components_list):
            common.append(comp)
        else:
            break

    if len(common) < 2:
        return None  # Too short to be meaningful

    # Require at least 2 distinct subdirectories BELOW the prefix
    subdirs: set[str] = set()
    for comps in components_list:
        if len(comps) > len(common):
            subdirs.add(comps[len(common)])
    if len(subdirs) < 2:
        return None  # Single-directory task

    return tuple(common)


def _strip_path_prefix(text: str, prefix: tuple) -> str:
    """Strip common path prefix components from path-like substrings in *text*.

    Replaces occurrences of ``/prefix/rest`` or ``prefix/rest`` with ``/rest``,
    preserving the leading ``/`` so downstream tokenization on ``/`` still
    extracts the meaningful path components.
    """
    if not prefix or not text or "/" not in text:
        return text

    prefix_str = "/".join(prefix)
    escaped = re.escape(prefix_str)

    # Replace "/prefix/" → "/"  (most common case)
    text = re.sub(r"/" + escaped + r"/", "/", text, flags=re.IGNORECASE)
    # Replace leading "prefix/" without leading slash → "" (bare prefix)
    text = re.sub(r"(?i)^" + escaped + r"/", "", text)
    # Replace "/prefix" at end of string → "" (prefix-only path, trailing slash handled above)
    text = re.sub(r"(?i)/" + escaped + r"$", "", text)
    # Replace exact "prefix" at start → "" (single-component prefix at start)
    text = re.sub(r"(?i)^" + escaped + r"$", "", text)

    return text


def _tokenize_string(s: str, path_prefix: Optional[tuple] = None) -> "set[str]":
    """Split a string into word-like tokens, filtering noise.

    Keeps short numeric strings (1-5 chars) as they may be IDs/keys.
    Filters longer pure numbers which are likely measurements/quantities.

    If path_prefix is provided, it is stripped from path-like substrings
    before tokenization — this eliminates shared workspace-root components
    that would otherwise create false dependency edges.
    """
    if path_prefix:
        s = _strip_path_prefix(s, path_prefix)
    tokens: set[str] = set()
    parts = re.split(r'[\s,;:|(){}\[\]<>"\'=/]+', s.lower())
    for part in parts:
        part = part.strip('"\'').strip()
        if not part or len(part) > 100:
            continue
        # Short strings (1-5 chars) are likely domain-specific values or IDs.
        # Keep them even if they overlap with noise tokens (e.g. "on" is both
        # an SQL keyword and a meaningful status value; "set" is both SQL and
        # a tool_sandbox state value). Only filter UUID fragments.
        if len(part) <= 5:
            if len(part) >= 32 and all(c in '0123456789abcdef-' for c in part):
                continue  # UUID fragments
            tokens.add(part)
            continue
        if part in _NOISE_TOKENS:
            continue
        # For longer strings, filter pure numbers (measurements/quantities)
        if part.replace('.', '', 1).replace('-', '', 1).isdigit():
            continue
        if len(part) >= 32 and all(c in '0123456789abcdef-' for c in part):
            continue
        tokens.add(part)
    return tokens


_NOISE_TOKENS: frozenset[str] = frozenset({
    "null", "none", "true", "false", "undefined", "nan", "inf",
    "id", "type", "status", "success", "error", "ok",
    # SQL keywords — universal across all databases, would create false
    # dependency matches between query steps that happen to share them
    "select", "from", "where", "insert", "update", "delete", "create",
    "table", "into", "values", "set", "alter", "drop", "index",
    "join", "on", "and", "or", "not", "in", "as", "by",
    "order", "limit", "offset", "group", "having", "union",
    "count", "sum", "avg", "min", "max", "like", "between",
    "primary", "key", "foreign", "references", "constraint",
    # Generic data/tool noise tokens
    "data", "result", "page", "content", "text", "value",
    "number", "string", "array", "object", "field",
})


def _extract_semantic_tokens(text: str, path_prefix: Optional[tuple] = None) -> "set[str]":
    """Extract meaningful string tokens from raw result or argument values.

    Handles heterogeneous result formats:
    - Bare strings: whitespace/punctuation-split tokenization
    - JSON dicts/lists: recurse into all string leaves
    - MCP envelope (3-level): unwrap {meta, content[{text}], structuredContent}
    """
    tokens: set[str] = set()
    if not text or not text.strip():
        return tokens

    # 1. Try JSON parse
    parsed = None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    if parsed is not None:
        if isinstance(parsed, dict):
            # Unwrap MCP envelope: structuredContent first
            sc = parsed.get("structuredContent")
            if isinstance(sc, dict):
                inner = sc.get("result")
                if isinstance(inner, str):
                    try:
                        tokens.update(_collect_leaf_strings(json.loads(inner), path_prefix=path_prefix))
                    except (json.JSONDecodeError, TypeError):
                        tokens.update(_tokenize_string(inner, path_prefix))
                else:
                    tokens.update(_collect_leaf_strings(sc, path_prefix=path_prefix))
                for k in ("result", "data", "response"):
                    v = sc.get(k)
                    if isinstance(v, str) and v not in (inner or ""):
                        tokens.update(_tokenize_string(v, path_prefix))
                    elif isinstance(v, (dict, list)):
                        tokens.update(_collect_leaf_strings(v, path_prefix=path_prefix))

            # Also try content[{text}] pattern (MCP content array)
            content_list = parsed.get("content", [])
            if isinstance(content_list, list):
                for item in content_list:
                    if isinstance(item, dict):
                        txt = item.get("text", "")
                        if isinstance(txt, str) and txt.strip():
                            try:
                                inner = json.loads(txt)
                                tokens.update(_collect_leaf_strings(inner, path_prefix=path_prefix))
                            except (json.JSONDecodeError, TypeError):
                                tokens.update(_tokenize_string(txt, path_prefix))

            # If no structured content yielded tokens, parse the whole dict
            if not tokens:
                tokens.update(_collect_leaf_strings(parsed, path_prefix=path_prefix))
        elif isinstance(parsed, list):
            tokens.update(_collect_leaf_strings(parsed, path_prefix=path_prefix))
        elif isinstance(parsed, str):
            tokens.update(_tokenize_string(parsed, path_prefix))
    else:
        # 2. Bare string
        tokens.update(_tokenize_string(text, path_prefix))

    return tokens


def _extract_arg_tokens(arguments: Dict[str, Any], path_prefix: Optional[tuple] = None) -> "set[str]":
    """Extract semantic tokens from ALL argument values regardless of key name."""
    tokens: set[str] = set()
    if not isinstance(arguments, dict):
        return tokens

    for val in arguments.values():
        if val is None:
            continue
        if isinstance(val, str):
            if val.strip() and val.strip() not in ("{}", "[]", "null", "None", ""):
                tokens.update(_tokenize_string(val, path_prefix))
        elif isinstance(val, (bool, int, float)):
            continue
        elif isinstance(val, dict):
            tokens.update(_collect_leaf_strings(val, path_prefix=path_prefix))
        elif isinstance(val, (list, tuple)):
            for item in val:
                if isinstance(item, str):
                    tokens.update(_tokenize_string(item, path_prefix))
                elif isinstance(item, dict):
                    tokens.update(_collect_leaf_strings(item, path_prefix=path_prefix))

    return tokens


# ── mutation classification (universal fallback via tool_metadata keywords) ──

# Imported lazily to avoid circular imports; fallback constants defined here.
_READ_ONLY_KEYWORDS: frozenset[str] = frozenset({
    "list", "read", "get", "search", "find", "show", "display",
    "info", "stat", "tree", "allowed",
})
_WRITE_KEYWORDS: frozenset[str] = frozenset({
    "write", "edit", "create", "mkdir", "move", "delete", "remove",
    "rename", "copy", "append", "modify", "update", "set",
})


def _is_likely_mutation(
    tool_name: str, read_only_tools: Optional[List[str]] = None,
) -> bool:
    """Classify a tool call as mutation using available signals.

    Priority:
    1. Explicit read_only_tools list: if tool is NOT in it → mutation
    2. Keyword inference: has write keyword but no read keyword → mutation
    3. Default: False (conservative — only classify as mutation when clear)
    """
    low = (tool_name or "").lower()
    if read_only_tools:
        if low not in read_only_tools:
            return True
        return False
    # Split on underscores so "stat" won't match "status", "get" won't
    # match "target", etc. — substring matching creates false positives.
    parts = set(low.split("_"))
    has_write = bool(parts & _WRITE_KEYWORDS)
    has_read = bool(parts & _READ_ONLY_KEYWORDS)
    if has_write and not has_read:
        return True
    return False


class UniversalToolSelector:
    """Universal tool sequence selection via data-flow dependency analysis.

    Replaces hardcoded tool-name keywords, parameter-key whitelists, and
    arbitrary max_selected cutoffs with a six-phase algorithm:

    Phase 1: Extract semantic tokens from every call (args + result)
    Phase 2: Build data-flow dependency graph (A's result tokens in B's args)
    Phase 3: Identify terminal calls (last success + mutations in final 40%)
    Phase 4: Backward reachability from terminals
    Phase 5: Add recovery chains (failed calls corrected by later successes)
    Phase 6: Dedup + exploration-artifact filter

    No max_selected — the dependency graph naturally determines trajectory length.
    """

    # ── public API ──────────────────────────────────────────────────────

    def __init__(
        self,
        tool_name_noise_extra: Optional[List[str]] = None,
        tool_name_noise_exclude: Optional[List[str]] = None,
    ):
        """Initialize with optional per-world TOOL_NAME_NOISE overrides.

        Args:
            tool_name_noise_extra: Tokens to ADD to the default noise set.
            tool_name_noise_exclude: Tokens to REMOVE from the default noise set.
        """
        if tool_name_noise_exclude or tool_name_noise_extra:
            noise = set(UniversalToolSelector._TOOL_NAME_NOISE)
            if tool_name_noise_exclude:
                noise.difference_update(tool_name_noise_exclude)
            if tool_name_noise_extra:
                noise.update(tool_name_noise_extra)
            self._TOOL_NAME_NOISE = frozenset(noise)
        else:
            self._TOOL_NAME_NOISE = UniversalToolSelector._TOOL_NAME_NOISE

    def select(
        self,
        tool_calls: Iterable[Any],
        task_type: str,
        *,
        max_dependency_distance: int = 5,
        preserve_failure_recovery_chains: bool = True,
        dependency_relevance_filter: bool = True,
        verification_window: int = 3,
        state_evidence: Optional[Dict[str, Any]] = None,
        read_only_tools: Optional[List[str]] = None,
        min_desired: int = 2,
    ) -> ToolSequenceSelection:
        """Select task-relevant tool calls using universal data-flow analysis.

        Args:
            tool_calls: Raw tool calls from a trajectory.
            task_type: "mutation" or "retrieval".
            max_dependency_distance: Max step distance for dependency edges.
            preserve_failure_recovery_chains: Include corrected failure pairs.
            dependency_relevance_filter: Currently unused (kept for API compat).
            verification_window: Unused (kept for API compat).
            state_evidence: Optional trajectory-level state change evidence.
            read_only_tools: Optional list of read-only tool names.
        """
        # Phase 0: Normalize
        raw_calls = [
            self._normalize_call_for_selection(call, idx + 1)
            for idx, call in enumerate(tool_calls)
        ]

        # Detect common path prefix from raw calls (for dense-graph worlds
        # like filesystem where all paths share a workspace root).
        path_prefix = _detect_path_prefix(raw_calls)

        # Phase 1: Build semantic calls with tokens
        scalls = [
            self._build_semantic_call(call, idx, read_only_tools, path_prefix)
            for idx, call in enumerate(raw_calls)
        ]

        # Phase 2: Build data-flow dependency graph
        graph = self._build_dependency_graph(scalls, max_dependency_distance)

        # Phase 3: Identify terminals
        terminals = self._identify_terminals(scalls, task_type)
        if not terminals:
            for c in reversed(scalls):
                if c.success:
                    terminals.add(c.idx)
                    break
        if not terminals:
            return ToolSequenceSelection(
                dropped_calls=[ToolSequenceSelector._drop(call, "failed_or_empty") for call in raw_calls]
            )

        # Phase 4: Backward reachability
        selected_indices = self._backward_reachability(graph, len(scalls), terminals)

        # Phase 4b: Forward walk from terminals to capture verification calls
        # (e.g. get→set→get: the final get is a readback that depends on the
        # set terminal but backward reachability can't find it).
        for t in terminals:
            for dep in graph.get(t, ()):
                if dep not in selected_indices:
                    selected_indices.add(dep)

        # Phase 5: Recovery chains
        if preserve_failure_recovery_chains:
            self._add_recovery_chains(scalls, selected_indices)

        # Phase 5.5: Terminal affinity fallback for sparse graphs.
        # When backward reachability finds very few calls (common in worlds where
        # tools are independent with little data flow), expand by semantic affinity
        # to terminals — NOT a blind temporal window, but prioritized by signal
        # strength: tool-family overlap > shared arguments > shared results >
        # nearby mutations > temporal proximity (last resort).
        if len(selected_indices) < min_desired:
            self._expand_by_terminal_affinity(
                scalls, terminals, selected_indices, min_desired,
                max_dependency_distance,
            )

        # Phase 6: Dedup + filter
        self._dedup_and_filter(scalls, selected_indices, task_type)

        # Build output
        selected: List[Dict[str, Any]] = []
        dropped: List[Dict[str, Any]] = []
        for idx, call in enumerate(raw_calls):
            pair = (call.get("tool_name", ""), _focus(call.get("arguments", {})))
            if idx in selected_indices:
                if _has_exploration_artifacts(call.get("arguments", {})):
                    dropped.append(ToolSequenceSelector._drop(call, "exploration_artifact"))
                    continue
                row = dict(call)
                row["selection_reason"] = ToolSequenceSelector._selection_reason(
                    call, task_type, raw_calls, idx, selected_indices,
                )
                selected.append(row)
            else:
                reason = "unrelated_exploration"
                if not call.get("success", True):
                    reason = "uncorrected_or_unrelated_failure"
                elif _has_exploration_artifacts(call.get("arguments", {})):
                    reason = "exploration_artifact"
                dropped.append(ToolSequenceSelector._drop(call, reason))

        # Safety cap (not a max_selected — dependency graph determines length)
        if len(selected) > _SAFETY_CAP:
            logger.warning(
                "UniversalToolSelector produced %d selected calls (safety cap %d). "
                "This may indicate degenerate dependencies — truncating to safety cap.",
                len(selected), _SAFETY_CAP,
            )
            overflow = selected[_SAFETY_CAP:]
            selected = selected[:_SAFETY_CAP]
            dropped.extend(
                ToolSequenceSelector._drop(call, "over_safety_cap") for call in overflow
            )

        for new_step, call in enumerate(selected, start=1):
            call["step"] = new_step
        return ToolSequenceSelection(selected_calls=selected, dropped_calls=dropped)

    # ── Phase 0/1: Normalization and token extraction ───────────────────

    @staticmethod
    def _normalize_call_for_selection(call: Any, source_step: int) -> Dict[str, Any]:
        """Normalize a raw tool call into a dict (same format as ToolSequenceSelector)."""
        return ToolSequenceSelector._normalize_call(call, source_step)

    @staticmethod
    def _build_semantic_call(
        call: Dict[str, Any], idx: int, read_only_tools: Optional[List[str]],
        path_prefix: Optional[tuple] = None,
    ) -> _SemanticCall:
        result_text = str(call.get("result") or "")
        args = call.get("arguments", {}) or {}
        tool_name = call.get("tool_name", "")
        return _SemanticCall(
            idx=idx,
            source_step=call.get("source_step", idx + 1),
            tool_name=tool_name,
            arguments=args,
            result_text=result_text,
            success=bool(call.get("success", True)),
            error_message=call.get("error_message"),
            arg_tokens=_extract_arg_tokens(args, path_prefix),
            result_tokens=_extract_semantic_tokens(result_text, path_prefix),
            is_mutation=_is_likely_mutation(tool_name, read_only_tools),
        )

    # ── Phase 2: Dependency graph ───────────────────────────────────────

    # Common tool-name tokens that don't indicate domain family membership.
    _TOOL_NAME_NOISE: frozenset[str] = frozenset({
        "get", "set", "list", "create", "delete", "update", "search", "find",
        "check", "show", "read", "write", "add", "remove", "query", "fetch",
        "modify", "change", "toggle", "enable", "disable", "run", "execute",
        "start", "stop", "open", "close", "status", "info", "data", "all",
        "new", "edit", "view", "make", "build", "load", "save", "export",
        "import", "sync", "push", "pull", "copy", "move", "rename",
    })

    def _tool_family_tokens(self, tool_name: str) -> "set[str]":
        """Extract domain-identifying tokens from a tool name.

        Splits on underscores/dashes and removes common verb prefixes,
        suffixes like 'status'/'info', and noise words.  The remaining tokens
        identify the tool's *domain* (e.g. "wifi", "cellular", "bluetooth",
        "github", "filesystem").
        """
        parts = re.split(r'[_\-.]+', tool_name.lower())
        return {p for p in parts if p and p not in self._TOOL_NAME_NOISE}

    def _build_dependency_graph(
        self, calls: List[_SemanticCall], max_distance: int,
    ) -> Dict[int, set[int]]:
        """Build directed graph: edge A→B means B depends on data from A's result.

        Three edge types (in priority order):
        1. Hard data-flow: A's result tokens appear in B's arguments.
        2. Soft data-flow: A and B share both result and argument tokens.
        3. Tool-family: nearby calls share domain tokens (captures get→set→verify
           chains where getters have no arguments and can't form data-flow edges).
        """
        graph: Dict[int, set[int]] = {}
        half_dist = max(1, max_distance // 2)

        for i, call_a in enumerate(calls):
            end = min(len(calls), i + 1 + max_distance)
            for j in range(i + 1, end):
                call_b = calls[j]
                # Type 1: Hard data-flow edge
                if call_a.result_tokens and (call_a.result_tokens & call_b.arg_tokens):
                    graph.setdefault(i, set()).add(j)
                    continue
                # Type 2: Soft shared-target edge
                if (call_a.result_tokens and call_b.result_tokens
                        and (call_a.result_tokens & call_b.result_tokens)
                        and call_a.arg_tokens and call_b.arg_tokens
                        and (call_a.arg_tokens & call_b.arg_tokens)):
                    graph.setdefault(i, set()).add(j)
                    continue
                # Type 3: Tool-family temporal edge (only within half distance)
                if j - i <= half_dist:
                    a_family = self._tool_family_tokens(call_a.tool_name)
                    if a_family:
                        b_family = self._tool_family_tokens(call_b.tool_name)
                        if a_family & b_family:
                            graph.setdefault(i, set()).add(j)

        return graph

    # ── Phase 3: Terminal identification ────────────────────────────────

    @staticmethod
    def _identify_terminals(
        calls: List[_SemanticCall], task_type: str,
    ) -> set[int]:
        """Find terminal calls — the leaves of the task execution tree."""
        terminals: set[int] = set()
        successful = [(i, c) for i, c in enumerate(calls) if c.success]
        if not successful:
            return terminals

        # Last successful call is always a terminal
        terminals.add(successful[-1][0])

        # For mutation tasks: include mutation calls in the latter 40%
        if str(task_type).lower() == "mutation":
            cutoff = max(0, len(calls) * 6 // 10)
            for i, c in successful:
                if i >= cutoff and c.is_mutation:
                    terminals.add(i)

        return terminals

    # ── Phase 4: Backward reachability ──────────────────────────────────

    @staticmethod
    def _backward_reachability(
        graph: Dict[int, set[int]], num_calls: int, terminals: set[int],
    ) -> set[int]:
        """Walk backward from terminals — all reachable calls are task-relevant."""
        reverse_graph: Dict[int, set[int]] = {}
        for caller, dependents in graph.items():
            for dep in dependents:
                reverse_graph.setdefault(dep, set()).add(caller)

        reachable: set[int] = set()
        stack = list(terminals)

        while stack:
            node = stack.pop()
            if node in reachable:
                continue
            reachable.add(node)
            for caller in reverse_graph.get(node, ()):
                if caller not in reachable:
                    stack.append(caller)

        return reachable

    # ── Phase 5: Recovery chains ────────────────────────────────────────

    @staticmethod
    def _add_recovery_chains(
        calls: List[_SemanticCall], selected_indices: set[int],
    ) -> None:
        """Add failure→success recovery pairs reachable from selected calls."""
        for i, call in enumerate(calls):
            if call.success:
                continue
            if not _has_useful_failure_feedback_raw(call):
                continue
            for j in range(i + 1, len(calls)):
                later = calls[j]
                if not later.success:
                    continue
                # Token overlap in arguments = retry on same target
                shared = call.arg_tokens & later.arg_tokens
                if shared and j in selected_indices:
                    selected_indices.add(i)
                    break
                # Cross-tool strategy: failure's result tokens match a selected success's args
                if call.result_tokens:
                    for sel_idx in selected_indices:
                        if call.result_tokens & calls[sel_idx].arg_tokens:
                            selected_indices.add(i)
                            selected_indices.add(j)
                            break

    # ── Phase 6: Dedup and filter ───────────────────────────────────────

    # ── Phase 5.5: Terminal affinity fallback ─────────────────────────────

    def _expand_by_terminal_affinity(
        self, calls: List[_SemanticCall], terminals: set[int],
        selected_indices: set[int], min_desired: int, max_distance: int,
    ) -> None:
        """Expand sparse selections by semantic affinity to terminals.

        When the dependency graph yields too few calls (common in worlds with
        independent tools and little data flow), this adds calls ranked by
        signal strength, not blind temporal proximity:

        Level A — tool-family overlap with a terminal (same domain)
        Level B — argument-token overlap with a terminal (same target entity)
        Level C — result-token overlap with a terminal (same observation domain)
        Level D — mutation within 2× max_distance of a terminal
        Level E — temporal proximity (closest unselected to any terminal)
        """
        search_radius = max_distance * 2
        all_indices = set(range(len(calls)))
        candidates = all_indices - selected_indices

        affinity_levels = [
            ("A", self._affinity_level_a),
            ("B", self._affinity_level_b),
            ("C", self._affinity_level_c),
            ("D", self._affinity_level_d),
            ("E", self._affinity_level_e),
        ]

        for _level_name, check_fn in affinity_levels:
            if len(selected_indices) >= min_desired:
                return
            # Collect candidates at this level that are within search radius
            batch: set[int] = set()
            for c in sorted(candidates):
                if c in batch:
                    continue
                # Must be within search_radius of at least one terminal
                in_range = any(abs(c - t) <= search_radius for t in terminals)
                if not in_range:
                    continue
                if check_fn(c, calls, terminals):
                    batch.add(c)
            if batch:
                selected_indices.update(batch)
                candidates -= batch

    def _affinity_level_a(self, idx: int, calls: List[_SemanticCall], terminals: set[int]) -> bool:
        """Tool-family overlap: candidate shares domain tokens with any terminal."""
        fam = self._tool_family_tokens(calls[idx].tool_name)
        if not fam:
            return False
        return any(
            bool(fam & self._tool_family_tokens(calls[t].tool_name))
            for t in terminals
        )

    @staticmethod
    def _affinity_level_b(idx: int, calls: List[_SemanticCall], terminals: set[int]) -> bool:
        """Arg-arg overlap: candidate and any terminal target the same entity."""
        a_tokens = calls[idx].arg_tokens
        if not a_tokens:
            return False
        return any(bool(a_tokens & calls[t].arg_tokens) for t in terminals)

    @staticmethod
    def _affinity_level_c(idx: int, calls: List[_SemanticCall], terminals: set[int]) -> bool:
        """Result-result overlap: candidate and any terminal observe the same domain."""
        r_tokens = calls[idx].result_tokens
        if not r_tokens:
            return False
        return any(bool(r_tokens & calls[t].result_tokens) for t in terminals)

    @staticmethod
    def _affinity_level_d(idx: int, calls: List[_SemanticCall], terminals: set[int]) -> bool:
        """Mutation proximity: candidate is a state change near any terminal."""
        return calls[idx].is_mutation

    @staticmethod
    def _affinity_level_e(idx: int, calls: List[_SemanticCall], terminals: set[int]) -> bool:
        """Temporal proximity (last resort): always true — closest candidates win."""
        return True

    # ── Phase 6: Dedup and filter ───────────────────────────────────────

    @staticmethod
    def _dedup_and_filter(
        calls: List[_SemanticCall], selected_indices: set[int], task_type: str,
    ) -> None:
        """Remove redundant calls and exploration artifacts from selected set.

        Only deduplicates *consecutive* identical calls (same tool + same args).
        Non-consecutive repetitions — e.g. get→set→get→set→get verification
        chains — are preserved because intervening mutations give each getter a
        distinct verification role.
        """
        # Group by (tool_name, frozenset(arg_tokens))
        groups: Dict[tuple, List[int]] = {}
        for idx in sorted(selected_indices):
            call = calls[idx]
            key = (call.tool_name, frozenset(call.arg_tokens))
            groups.setdefault(key, []).append(idx)

        for group_indices in groups.values():
            if len(group_indices) <= 2:
                continue
            # Split into consecutive runs; only dedup within each run
            sorted_grp = sorted(group_indices)
            run_start = 0
            for i in range(1, len(sorted_grp)):
                if sorted_grp[i] - sorted_grp[i - 1] > 1:
                    run = sorted_grp[run_start:i]
                    if len(run) > 2:
                        for mid in run[1:-1]:
                            selected_indices.discard(mid)
                    run_start = i
            run = sorted_grp[run_start:]
            if len(run) > 2:
                for mid in run[1:-1]:
                    selected_indices.discard(mid)

        # Remove calls with exploration artifacts or no meaningful content
        for idx in list(selected_indices):
            call = calls[idx]
            if _has_exploration_artifacts(call.arguments):
                selected_indices.discard(idx)
            elif not call.arg_tokens and not call.result_tokens:
                selected_indices.discard(idx)


def _has_useful_failure_feedback_raw(call: _SemanticCall) -> bool:
    """Check if a failed _SemanticCall has actionable feedback (not just parse errors)."""
    feedback = f"{call.result_text} {call.error_message or ''}".strip().lower()
    if not feedback:
        return False
    low_tool = call.tool_name.lower()
    if "nonexistent" in low_tool or "unknown_tool" in low_tool:
        return False
    low_value = (
        "invalid json", "schema validation", "missing required",
        "tool not found", "unknown tool", "parse error",
    )
    return not any(marker in feedback for marker in low_value)


_SAFETY_CAP = 50


def synthesize_problem_from_evidence(
    *,
    task_type: str,
    state_evidence: Optional[Dict[str, Any]],
    selected_calls: List[Dict[str, Any]],
    retrieval_spec: Optional[Any],
    language: str = "en",
) -> ReplayProblemSpec:
    normalized_task_type = str(task_type).lower()
    evidence_summary = _evidence_summary(state_evidence, retrieval_spec, selected_calls)
    if normalized_task_type == TaskType.MUTATION.value:
        problem, expected = _mutation_problem_from_selected_calls(selected_calls, state_evidence)
    else:
        problem, expected = _retrieval_problem_from_evidence(retrieval_spec, selected_calls)
    judge = _judge_problem_utility(problem, normalized_task_type, evidence_summary)
    return ReplayProblemSpec(
        problem=problem,
        task_type=normalized_task_type,
        evidence_summary=evidence_summary,
        expected_outcome=expected,
        required_tools_hint=[call.get("tool_name", "") for call in selected_calls],
        judge=judge,
        reference_answer=str(expected.get("reference_answer", "")),
    )


async def synthesize_problem_via_llm(
    *,
    maas_client: Any,
    model_config: Any,
    task_type: str,
    state_evidence: Optional[Dict[str, Any]],
    selected_calls: List[Dict[str, Any]],
    language: str = "en",
    world_context: Optional[Dict[str, Any]] = None,
) -> ReplayProblemSpec:
    """Use LLM to generate a natural-language problem from evidence and selected tool calls.

    The LLM receives compact evidence (state summary + tool names + world context),
    NOT trajectory messages. Generates 2 candidates and picks the better one.
    Falls back to rule-based synthesis if LLM fails.
    """
    evidence_text = _build_compact_evidence(state_evidence, selected_calls)
    tool_list = [call.get("tool_name", "") for call in selected_calls]
    wc_text = _format_world_context(world_context)

    if language == "zh":
        system_prompt = (
            "你是一个为工具调用训练数据生成用户任务的助手。"
            "根据给定的状态变化证据和实际使用的工具（包含参数和结果），"
            "生成一个自然的、面向行动的用户请求。"
            "关键要求：任务必须忠实反映证据中展示的实际操作。"
            "阅读参数值（电话号码、消息内容、查询字符串、文件路径等）"
            "并用它们来 grounding 问题。例如，如果工具向特定联系人发送了生日祝福消息，"
            "任务必须关于发送这些消息——而不是生成随机字符串或不相关的操作。"
            "不要提及具体工具名称，不要分步骤描述，不要反问或请求确认。"
            "只输出一个简洁明确的用户任务描述。"
        )
        user_prompt = (
            f"实际工具操作证据（包含参数和结果）：\n{evidence_text}\n\n"
            f"涉及的工具类别：{', '.join(tool_list)}\n"
            f"任务类型：{'修改系统状态' if task_type == 'mutation' else '查询信息'}\n\n"
            f"请基于以上证据生成用户任务描述，使用参数中的具体细节使任务具体且有根据。"
        )
    else:
        system_prompt = (
            "You generate user tasks for tool-calling training data. "
            "Given state change evidence and the EXACT tools used (with their actual arguments and results), "
            "produce a natural, action-oriented user request that a real user might have asked. "
            "CRITICAL: The task MUST faithfully reflect the actual operations shown in the evidence. "
            "Read the argument values (phone numbers, message content, query strings, file paths, etc.) "
            "and use them to ground the problem. For example, if tools sent messages to specific contacts "
            "with birthday greetings, the task must be about sending those messages — NOT about generating "
            "random strings or unrelated operations. "
            "Do NOT mention specific tool names. Do NOT give step-by-step instructions. "
            "Do NOT ask questions or request confirmation. "
            "Output ONLY in English. Never mix in Chinese characters, fullwidth punctuation, or other non-English scripts. "
            "Output only a concise, clear user task description on a single line."
        )
        user_prompt = (
            f"Evidence of actual tool operations (with arguments and results):\n{evidence_text}\n\n"
            f"Tool categories involved: {', '.join(tool_list)}\n"
            f"Task type: {'mutate system state' if task_type == 'mutation' else 'retrieve information'}\n\n"
            f"Based on the evidence above, what user task would naturally require these exact tool operations? "
            f"Use specific details from the arguments (names, phone numbers, queries, etc.) "
            f"to make the task concrete and grounded."
        )

    if wc_text:
        user_prompt = f"World context:\n{wc_text}\n\n{user_prompt}"

    # Generate up to 4 attempts to get 2 clean candidates.
    # For English: reject Chinese/garbled artifacts. For Chinese: skip detection.
    is_chinese = language == "zh"
    candidates: List[str] = []
    for attempt in range(4):
        if len(candidates) >= 2:
            break
        try:
            resp_str = await maas_client.generate_text(
                user_prompt,
                model_config,
                system_prompt=system_prompt,
            )
            raw_text = resp_str or ""
            if not is_chinese and _contains_chinese(raw_text):
                # Reject garbled output and retry with stronger prompt
                user_prompt_retry = (
                    f"{user_prompt}\n\nCRITICAL: Your previous response contained Chinese characters. "
                    f"Output ONLY plain English text. No Chinese, no special characters."
                )
                resp_str = await maas_client.generate_text(
                    user_prompt_retry,
                    model_config,
                    system_prompt=system_prompt,
                )
            problem_text = _sanitize_deepseek_tokens(resp_str or "", clean_garbled=not is_chinese)
            if problem_text.startswith("```"):
                lines = problem_text.split("\n")
                problem_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            problem_text = _sanitize_deepseek_tokens(problem_text, clean_garbled=not is_chinese)
            if problem_text and len(problem_text) >= 10:
                if is_chinese or not _contains_chinese(problem_text):
                    candidates.append(problem_text)
        except Exception:
            logger.debug("LLM problem synthesis candidate generation failed", exc_info=True)
            continue

    if not candidates:
        return synthesize_problem_from_evidence(
            task_type=task_type,
            state_evidence=state_evidence,
            selected_calls=selected_calls,
            retrieval_spec=None,
            language=language,
        )

    # Pick the candidate with the best utility judge score
    best_problem = candidates[0]
    best_judge = _judge_problem_utility(best_problem, task_type, evidence_text)
    for candidate in candidates[1:]:
        candidate_judge = _judge_problem_utility(candidate, task_type, evidence_text)
        if not best_judge.get("consistent") and candidate_judge.get("consistent"):
            best_problem = candidate
            best_judge = candidate_judge
        elif best_judge.get("consistent") and candidate_judge.get("consistent"):
            if candidate_judge.get("utility") == "high" and best_judge.get("utility") != "high":
                best_problem = candidate
                best_judge = candidate_judge

    return ReplayProblemSpec(
        problem=best_problem,
        task_type=str(task_type).lower(),
        evidence_summary=evidence_text,
        expected_outcome={"state_hashes": {}},
        required_tools_hint=tool_list,
        judge=best_judge,
        reference_answer="",
    )


def _extract_args_summary(call: Dict[str, Any]) -> str:
    """Extract a compact argument summary for evidence building.

    Returns meaningful argument values (not empty JSON or boilerplate)
    so the LLM can ground the problem in what the tools ACTUALLY did.
    """
    args = call.get("arguments", {}) if isinstance(call.get("arguments"), dict) else {}
    if not args:
        return "(no arguments)"
    parts: List[str] = []
    # Keys that carry the primary semantic payload — ordered by informativeness
    primary_keys = (
        "phone_number", "recipient", "content", "message",
        "query", "name", "path", "file", "target",
        "reminder_id", "person_id", "contact_id",
    )
    seen: set[str] = set()
    for key in primary_keys:
        val = args.get(key)
        if val is not None and key not in seen:
            str_val = str(val).strip()
            if str_val and str_val not in ("{}", "[]", "null", "None"):
                # Truncate long content values but keep enough to convey intent
                if key in ("content", "message") and len(str_val) > 80:
                    str_val = str_val[:77] + "..."
                elif len(str_val) > 120:
                    str_val = str_val[:117] + "..."
                parts.append(f"{key}='{str_val}'")
                seen.add(key)
    # Fallback: include boolean/status-style keys if primary keys were empty
    if not parts:
        for key in ("enabled", "status", "value", "mode"):
            val = args.get(key)
            if val is not None and key not in seen:
                str_val = str(val).strip()
                if str_val:
                    parts.append(f"{key}={str_val}")
                    seen.add(key)
    if not parts:
        # Last resort: include first 2 non-empty kv pairs
        count = 0
        for k, v in args.items():
            if count >= 2:
                break
            sv = str(v).strip()
            if sv and sv not in ("{}", "[]", "null", "None"):
                parts.append(f"{k}={sv[:80]}")
                count += 1
    return ", ".join(parts) if parts else "(no arguments)"


def _build_compact_evidence(
    state_evidence: Optional[Dict[str, Any]],
    selected_calls: List[Dict[str, Any]],
) -> str:
    """Build a compact evidence summary for LLM problem synthesis.

    Includes tool names, their actual argument values, and result previews
    so the LLM can generate a problem grounded in what the tools actually did.
    """
    parts = []
    if isinstance(state_evidence, dict):
        summary = state_evidence.get("summary") or ""
        if summary:
            parts.append(f"State changes: {summary}")
    for call in selected_calls:
        name = call.get("tool_name", "")
        args_summary = _extract_args_summary(call)
        success_mark = "" if call.get("success", True) else " [FAILED]"
        result_preview = str(call.get("result", ""))[:200]
        parts.append(
            f"Tool '{name}' called with {args_summary}{success_mark} → {result_preview}"
        )
    return "\n".join(parts)


def build_admin_replay_reset_body(
    *,
    original_reset_meta: Optional[Dict[str, Any]],
    fallback_seed: Optional[int] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {}
    if fallback_seed is not None:
        body["seed"] = fallback_seed
    if isinstance(original_reset_meta, dict):
        for key in ("task_id", "category", "selected_domain"):
            if original_reset_meta.get(key) is not None:
                body[key] = original_reset_meta[key]
    return body


async def restore_admin_replay_s0(
    *,
    mcp_client: Any,
    original_reset_meta: Optional[Dict[str, Any]],
    fallback_seed: Optional[int] = None,
) -> Dict[str, Any]:
    if not hasattr(mcp_client, "admin_request"):
        raise RuntimeError("admin_request is required for admin replay reset")
    body = build_admin_replay_reset_body(
        original_reset_meta=original_reset_meta,
        fallback_seed=fallback_seed,
    )
    return await mcp_client.admin_request("/admin/reset", method="POST", body=body)



def verify_replay_state(
    *,
    original_s1: Any,
    replay_s1: Any,
    task_type: str,
    expected_outcome: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if str(task_type).lower() == TaskType.RETRIEVAL.value:
        return {"verified": True, "strategy": "retrieval_evidence", "reason": "retrieval replay has no required state change"}
    subset_verification = _verify_expected_hash_subset(replay_s1, expected_outcome)
    if subset_verification is not None:
        return subset_verification
    if isinstance(original_s1, dict) and isinstance(replay_s1, dict):
        original_view = _state_hash_view(original_s1)
        replay_view = _state_hash_view(replay_s1)
        if original_view and replay_view:
            return {
                "verified": original_view == replay_view,
                "strategy": "admin_state_hash_exact",
                "original": original_view,
                "replay": replay_view,
            }
    if expected_outcome:
        return {
            "verified": True,
            "strategy": "expected_outcome_recorded",
            "expected_outcome": expected_outcome,
        }
    return {"verified": False, "strategy": "unsupported", "reason": "no comparable state evidence"}


def build_replay_review_record(
    *,
    problem: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    metadata: Dict[str, Any],
    judge_result: Optional[Dict[str, Any]] = None,
    world_context: Optional[Dict[str, Any]] = None,
    execution_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if judge_result:
        record = {
            "record_id": str(uuid.uuid4()),
            "problem": problem,
            "messages": messages,
            "tools": tools,
            "source_mode": (execution_meta or {}).get("execution_path", "replay_synthesis"),
            "quality_tier": judge_result.get("quality_tier", "acceptable"),
            "quality_score": judge_result.get("quality_score", 0.7),
            "hard_judge_pass": judge_result.get("hard_judge_pass", True),
            "hard_judge_reason": judge_result.get("hard_judge_reason", ""),
            "soft_judge_pass": judge_result.get("soft_judge_pass", True),
            "soft_judge_severity": judge_result.get("soft_judge_severity", ""),
            "soft_judge_issues": judge_result.get("soft_judge_issues", []),
            "selected_for_training": judge_result.get("selected_for_training", True),
            "trajectory_accept_mode": "replay_synthesis_judged",
            "quality_selection_reason": (
                f"judge_score_{judge_result.get('quality_score', 0.7):.2f}"
                f"{'_severity_' + judge_result.get('soft_judge_severity', '') if judge_result.get('soft_judge_severity') else ''}"
            ),
        }
    else:
        record = {
            "record_id": str(uuid.uuid4()),
            "problem": problem,
            "messages": messages,
            "tools": tools,
            "source_mode": "replay_synthesis",
            "quality_tier": "acceptable",
            "quality_score": 0.70,
            "hard_judge_pass": False,
            "hard_judge_reason": "no_judge_available",
            "soft_judge_pass": False,
            "soft_judge_severity": "",
            "soft_judge_issues": [],
            "selected_for_training": False,
            "trajectory_accept_mode": "replay_synthesis_verified",
            "quality_selection_reason": "replay_unjudged_fallback",
        }
    if world_context:
        record.setdefault("world_context", {}).update(world_context)
    if execution_meta:
        record["execution_meta"] = execution_meta
    record.update(metadata or {})
    return record


class ReplaySynthesisRunner:
    def __init__(self, config: Optional[ReplaySynthesisConfig] = None):
        self.config = config or ReplaySynthesisConfig()
        selection_strategy = self.config.tool_sequence_selection
        if selection_strategy == "universal":
            self.selector: Any = UniversalToolSelector(
                tool_name_noise_extra=self.config.tool_name_noise_extra,
                tool_name_noise_exclude=self.config.tool_name_noise_exclude,
            )
        else:
            self.selector: Any = ToolSequenceSelector()

    async def run(
        self,
        *,
        trajectory: Any,
        task_type: str,
        state_evidence: Optional[Dict[str, Any]],
        retrieval_spec: Optional[Any],
        mcp_client: Any,
        tools: List[Dict[str, Any]],
        original_s1: Any = None,
        artifact_dir: Optional[Path] = None,
        language: str = "en",
        maas_client: Any = None,
        model_config: Any = None,
        harness_model_config: Any = None,
        polish_model_config: Any = None,
        judge_model_config: Any = None,
        world_context: Optional[Dict[str, Any]] = None,
        read_only_tools: Optional[List[str]] = None,
    ) -> ReplaySynthesisResult:
        # ── Step 1: Select task-coherent tool subsequence ──
        if isinstance(self.selector, UniversalToolSelector):
            selection = self.selector.select(
                getattr(trajectory, "tool_calls", []) if trajectory is not None else [],
                task_type,
                max_dependency_distance=self.config.max_dependency_distance,
                preserve_failure_recovery_chains=self.config.preserve_failure_recovery_chains,
                dependency_relevance_filter=self.config.dependency_relevance_filter,
                state_evidence=state_evidence,
                read_only_tools=read_only_tools,
                min_desired=self.config.min_selected_tool_calls,
            )
        else:
            selection = self.selector.select(
                getattr(trajectory, "tool_calls", []) if trajectory is not None else [],
                task_type,
                max_selected=self.config.max_selected_tool_calls,
                max_selected_mutations=self.config.max_selected_mutations,
                max_dependency_distance=self.config.max_dependency_distance,
                preserve_failure_recovery_chains=self.config.preserve_failure_recovery_chains,
                dependency_relevance_filter=self.config.dependency_relevance_filter,
            )
        if not selection.selected_calls:
            return ReplaySynthesisResult(False, selection=selection, rejected_reason="no_selected_tool_calls")

        # ── Step 2: Synthesize problem ──
        if self.config.llm_problem_synthesis and maas_client and model_config:
            problem_spec = await synthesize_problem_via_llm(
                maas_client=maas_client,
                model_config=model_config,
                task_type=task_type,
                state_evidence=state_evidence,
                selected_calls=selection.selected_calls,
                language=language,
                world_context=world_context,
            )
        else:
            problem_spec = synthesize_problem_from_evidence(
                task_type=task_type,
                state_evidence=state_evidence,
                selected_calls=selection.selected_calls,
                retrieval_spec=retrieval_spec,
                language=language,
            )
        if not problem_spec.judge.get("consistent"):
            return ReplaySynthesisResult(
                False,
                problem_spec=problem_spec,
                selection=selection,
                rejected_reason=str(problem_spec.judge.get("reason", "problem_rejected")),
            )

        # ── Step 3: Execute selected tools, capture fresh results ──
        # Two paths:
        #   Path A — Harness mode ("full"/"strict"): model re-executes tools, producing
        #     natural task-oriented thoughts. No polish needed unless the model deviates
        #     from the expected tool sequence and we force template thoughts.
        #   Path B — Skeleton mode ("disabled"): deterministic replay + rule-based
        #     template thoughts, ALWAYS needs polish to convert rule-generated
        #     templates into natural, task-grounded reasoning.
        use_harness = (
            self.config.harness_mode != "disabled"
            and maas_client is not None
        )

        # Track execution metadata for debugging and data quality analysis.
        execution_meta: Dict[str, Any] = {
            "harness_mode": self.config.harness_mode,
            "execution_path": "unknown",
            "polish_applied": False,
            "forced_count": 0,
            "fallback_ratio": 0.0,
        }

        if use_harness:
            harness_model_cfg = harness_model_config or model_config
            messages, tool_results, final_response, forced_count = (
                await self._execute_harness_replay(
                    problem=problem_spec.problem,
                    selected_calls=selection.selected_calls,
                    mcp_client=mcp_client,
                    maas_client=maas_client,
                    model_config=harness_model_cfg,
                    tools=tools,
                    task_type=task_type,
                    language=language,
                    world_context=world_context,
                )
            )

            total_steps = len(selection.selected_calls)
            fallback_ratio = forced_count / max(total_steps, 1)
            execution_meta["forced_count"] = forced_count
            execution_meta["fallback_ratio"] = round(fallback_ratio, 3)

            if fallback_ratio >= self.config.harness_fallback_threshold:
                # Harness deviated too much — the model doesn't "get" this task.
                # Fall back to skeleton + polish for reliable output.
                logger.info(
                    "Harness forced-fallback ratio %.0f%% >= threshold %.0f%% — "
                    "falling back to skeleton + polish",
                    fallback_ratio * 100, self.config.harness_fallback_threshold * 100,
                )
                tool_results = await self._execute_selected_tools(
                    mcp_client, selection.selected_calls,
                )
                final_response = _final_response(
                    problem_spec, selection.selected_calls, tool_results,
                )
                skeleton = self.build_replay_messages(
                    problem=problem_spec.problem,
                    selected_calls=selection.selected_calls,
                    tool_results=tool_results,
                    final_response=final_response,
                )
                polish_available = (
                    self.config.polish_enabled
                    and maas_client is not None
                    and polish_model_config is not None
                )
                if polish_available:
                    polished = await self._polish_replay_trajectory(
                        maas_client=maas_client,
                        polish_model_config=polish_model_config,
                        problem=problem_spec.problem,
                        task_type=task_type,
                        selected_calls=selection.selected_calls,
                        tool_results=tool_results,
                        skeleton_messages=skeleton,
                        reference_answer=problem_spec.reference_answer,
                        world_context=world_context,
                        language=language,
                    )
                    messages = polished if polished is not None else skeleton
                    execution_meta["polish_applied"] = polished is not None
                else:
                    messages = skeleton
                execution_meta["execution_path"] = "harness_fallback_skeleton"
            elif forced_count > 0:
                # Minor deviations: some steps used forced template thoughts.
                # Polish to convert those template thoughts to natural task-grounded reasoning.
                polish_available = (
                    self.config.polish_enabled
                    and maas_client is not None
                    and polish_model_config is not None
                )
                if polish_available:
                    polished = await self._polish_replay_trajectory(
                        maas_client=maas_client,
                        polish_model_config=polish_model_config,
                        problem=problem_spec.problem,
                        task_type=task_type,
                        selected_calls=selection.selected_calls,
                        tool_results=tool_results,
                        skeleton_messages=messages,
                        reference_answer=problem_spec.reference_answer,
                        world_context=world_context,
                        language=language,
                    )
                    if polished is not None:
                        messages = polished
                        execution_meta["polish_applied"] = True
                execution_meta["execution_path"] = "harness_polished"
            else:
                # forced_count == 0 — all thoughts are natural, skip polish
                execution_meta["execution_path"] = "harness_natural"
        else:
            # Harness disabled: skeleton + always polish
            tool_results = await self._execute_selected_tools(
                mcp_client, selection.selected_calls,
            )
            final_response = _final_response(
                problem_spec, selection.selected_calls, tool_results,
            )
            skeleton = self.build_replay_messages(
                problem=problem_spec.problem,
                selected_calls=selection.selected_calls,
                tool_results=tool_results,
                final_response=final_response,
            )
            polish_available = (
                self.config.polish_enabled
                and maas_client is not None
                and polish_model_config is not None
            )
            if polish_available:
                polished = await self._polish_replay_trajectory(
                    maas_client=maas_client,
                    polish_model_config=polish_model_config,
                    problem=problem_spec.problem,
                    task_type=task_type,
                    selected_calls=selection.selected_calls,
                    tool_results=tool_results,
                    skeleton_messages=skeleton,
                    reference_answer=problem_spec.reference_answer,
                    world_context=world_context,
                    language=language,
                )
                messages = polished if polished is not None else skeleton
                execution_meta["polish_applied"] = polished is not None
                execution_meta["execution_path"] = "skeleton_polished"
            else:
                messages = skeleton
                execution_meta["execution_path"] = "skeleton_raw"

        # ── Step 5: Verify final state ──
        replay_s1 = None
        if self.config.verify_final_state and hasattr(mcp_client, "admin_request"):
            try:
                replay_s1 = await mcp_client.admin_request("/admin/state")
            except Exception:
                replay_s1 = None
                logger.warning("Failed to fetch replay S1 state via admin_request", exc_info=True)
        verification = verify_replay_state(
            original_s1=original_s1,
            replay_s1=replay_s1,
            task_type=task_type,
            expected_outcome=problem_spec.expected_outcome,
        )

        # ── Step 6: Judge quality (runs regardless of verification) ──
        judge_result = None
        if self.config.enable_quality_judge and maas_client and judge_model_config:
            score_weights = {
                "hard": self.config.judge_hard_weight,
                "soft": self.config.judge_soft_weight,
                "dual_bonus": self.config.judge_dual_bonus,
                "threshold_high": self.config.judge_threshold_high,
                "threshold_acceptable": self.config.judge_threshold_acceptable,
            }
            judge_result = await _judge_replay_trajectory(
                maas_client=maas_client,
                judge_model_config=judge_model_config,
                problem=problem_spec.problem,
                task_type=task_type,
                messages=messages,
                selected_calls=selection.selected_calls,
                reference_answer=problem_spec.reference_answer,
                world_context=world_context,
                score_weights=score_weights,
            )

        # Determine acceptance: quality judge is primary gate; verification
        # failure alone does not reject — it is recorded as a signal.
        accepted = True
        rejected_reason = ""
        if judge_result is not None:
            quality_score = judge_result.get("quality_score", 0)
            quality_tier = judge_result.get("quality_tier", "reject")
            min_tier = self.config.min_quality_tier
            if quality_tier == "reject" or (min_tier == "high_quality" and quality_tier == "acceptable"):
                accepted = False
                rejected_reason = f"quality_tier_{quality_tier}"
        elif self.config.verify_final_state and not verification.get("verified"):
            # No quality judge available; fall back to verification gate
            accepted = False
            rejected_reason = "verification_failed"

        review_record = build_replay_review_record(
            problem=problem_spec.problem,
            messages=messages,
            tools=tools,
            metadata={"task_type": task_type, "tool_steps": len(selection.selected_calls)},
            judge_result=judge_result,
            world_context=world_context,
            execution_meta=execution_meta,
        )
        result = ReplaySynthesisResult(
            accepted,
            problem_spec=problem_spec,
            selection=selection,
            messages=messages,
            tool_results=tool_results,
            verification=verification,
            review_record=review_record,
            rejected_reason=rejected_reason,
        )
        if artifact_dir is not None:
            result.artifact_dir = str(save_replay_artifacts(artifact_dir, result, tools))
        return result

    def build_skipped_result(
        self,
        *,
        trajectory: Any,
        task_type: str,
        state_evidence: Optional[Dict[str, Any]],
        retrieval_spec: Optional[Any],
        reason: str,
        language: str = "en",
        read_only_tools: Optional[List[str]] = None,
    ) -> ReplaySynthesisResult:
        if isinstance(self.selector, UniversalToolSelector):
            selection = self.selector.select(
                getattr(trajectory, "tool_calls", []) if trajectory is not None else [],
                task_type,
                state_evidence=state_evidence,
                read_only_tools=read_only_tools,
                min_desired=self.config.min_selected_tool_calls,
            )
        else:
            selection = self.selector.select(
                getattr(trajectory, "tool_calls", []) if trajectory is not None else [],
                task_type,
                max_selected=self.config.max_selected_tool_calls,
            )
        problem_spec = None
        if selection.selected_calls:
            problem_spec = synthesize_problem_from_evidence(
                task_type=task_type,
                state_evidence=state_evidence,
                selected_calls=selection.selected_calls,
                retrieval_spec=retrieval_spec,
                language=language,
            )
        return ReplaySynthesisResult(
            accepted=False,
            problem_spec=problem_spec,
            selection=selection,
            verification={"verified": False, "strategy": "skipped", "reason": reason},
            rejected_reason=reason,
        )

    @staticmethod
    def build_replay_messages(
        *,
        problem: str,
        selected_calls: List[Dict[str, Any]],
        tool_results: List[str],
        final_response: str,
    ) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": "You are a helpful agent that uses tools directly to complete the user's task."},
            {"role": "user", "content": problem},
        ]
        for idx, call in enumerate(selected_calls):
            tool_name = call.get("tool_name", "unknown_tool")
            args = call.get("arguments", {}) or {}
            call_id = f"replay_call_{idx + 1}"
            messages.append(
                {
                    "role": "assistant",
                    "content": _task_oriented_thought(tool_name, args, call.get("success", True)),
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": _safe_json_dumps(args, ensure_ascii=False),
                            },
                        }
                    ],
                }
            )
            result = tool_results[idx] if idx < len(tool_results) else ""
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
        messages.append({"role": "assistant", "content": final_response})
        return messages

    async def _execute_selected_tools(
        self,
        mcp_client: Any,
        selected_calls: List[Dict[str, Any]],
    ) -> List[str]:
        """Execute selected tools sequentially via MCP, no model involvement.

        Returns a list of formatted tool result strings, one per call.
        """
        results: List[str] = []
        for call in selected_calls:
            tool_name = call.get("tool_name", "")
            args = call.get("arguments", {}) or {}
            try:
                result = await mcp_client.call_tool(tool_name, args)
                results.append(_format_tool_result(result))
            except Exception as exc:
                logger.warning("Tool execution failed in replay: tool=%s args=%s error=%s", tool_name, args, exc)
                results.append(f"Tool execution error: {exc}")
        return results

    async def _polish_replay_trajectory(
        self,
        *,
        maas_client: Any,
        polish_model_config: Any,
        problem: str,
        task_type: str,
        selected_calls: List[Dict[str, Any]],
        tool_results: List[str],
        skeleton_messages: List[Dict[str, Any]],
        reference_answer: str = "",
        world_context: Optional[Dict[str, Any]] = None,
        language: str = "en",
    ) -> Optional[List[Dict[str, Any]]]:
        """Polish rule-generated skeleton messages into task-execution reasoning.

        Replicates DataSynthesisPipeline._polish_fallback_trajectory() logic
        but standalone in the replay module. Uses judge_model (low temp) to
        minimize hallucination.
        """
        from prompts.synthesis_judge import (
            POLISH_FALLBACK_TRAJECTORY_SYSTEM_PROMPT,
            POLISH_FALLBACK_TRAJECTORY_USER_TEMPLATE,
        )

        # Build compact tool sequence for global context.
        # Results are truncated to first 300 chars to avoid leaking long content
        # (PII, secrets) through the polish model while preserving context.
        tool_seq = []
        for idx, call in enumerate(selected_calls):
            result = tool_results[idx] if idx < len(tool_results) else ""
            tool_seq.append({
                "step": idx + 1,
                "tool_name": call.get("tool_name", ""),
                "arguments": call.get("arguments", {}),
                "result": str(result)[:300],
            })
        tool_sequence_json = json.dumps(tool_seq, ensure_ascii=False, indent=2)

        # Compact serialization: only include assistant thoughts + tool call names
        compact_msgs = []
        step_idx = 1
        for msg in skeleton_messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                compact_msgs.append({
                    "role": "assistant",
                    "content": msg.get("content", ""),
                    "tool_calls": [
                        {"function": {"name": tc.get("function", {}).get("name", "?")}}
                        for tc in (msg.get("tool_calls") or [])
                    ],
                })
            elif msg.get("role") == "tool":
                compact_msgs.append({
                    "role": "tool",
                    "content": f"[output for step {step_idx}]",
                })
                step_idx += 1
            else:
                compact_msgs.append(dict(msg))
        fallback_messages_json = json.dumps(compact_msgs, ensure_ascii=False, indent=2)

        wc_text = _format_world_context(world_context)
        polish_user = POLISH_FALLBACK_TRAJECTORY_USER_TEMPLATE.format(
            problem=problem,
            task_type=task_type,
            require_plan="false",
            require_final_answer="true",
            tool_sequence_json=tool_sequence_json,
            fallback_messages_json=fallback_messages_json,
            reference_answer=reference_answer or "N/A",
            critique="N/A",
        )
        if wc_text:
            polish_user = f"World context:\n{wc_text}\n\n{polish_user}"

        try:
            resp_str = await maas_client.generate_text(
                polish_user,
                polish_model_config,
                system_prompt=POLISH_FALLBACK_TRAJECTORY_SYSTEM_PROMPT,
            )
            polish_payload = _parse_json_from_response(resp_str)
            if not isinstance(polish_payload, dict):
                return None

            polished = self._apply_polish_to_messages(
                original_messages=skeleton_messages,
                polish_payload=polish_payload,
                selected_calls=selected_calls,
                tool_results=tool_results,
                problem=problem,
                reference_answer=reference_answer,
                task_type=task_type,
                language=language,
            )
            return polished
        except Exception:
            logger.warning("Polish step failed — falling back to skeleton", exc_info=True)
            return None

    def _apply_polish_to_messages(
        self,
        *,
        original_messages: List[Dict[str, Any]],
        polish_payload: Dict[str, Any],
        selected_calls: List[Dict[str, Any]],
        tool_results: List[str],
        problem: str,
        reference_answer: str,
        task_type: str,
        language: str = "en",
    ) -> Optional[List[Dict[str, Any]]]:
        """Apply LLM polish output to skeleton messages.

        Simplified version of DataSynthesisPipeline._apply_structured_rewrite().
        """
        steps_data = polish_payload.get("steps")
        if not isinstance(steps_data, list):
            return None

        keep_cjk = language == "zh"
        plan = _sanitize_deepseek_tokens((polish_payload.get("plan", "") or ""), clean_garbled=not keep_cjk)
        final_response = _sanitize_deepseek_tokens((polish_payload.get("final_response", "") or ""), clean_garbled=not keep_cjk)

        thought_by_step: Dict[int, str] = {}
        for row in steps_data:
            if not isinstance(row, dict):
                continue
            try:
                step_id = int(row.get("step"))
            except Exception:
                continue
            thought = _sanitize_deepseek_tokens(str(row.get("thought", "")), clean_garbled=not keep_cjk)
            if step_id > 0 and thought:
                thought_by_step[step_id] = thought

        # Fill in missing thoughts with enhanced task-oriented defaults
        for step in range(1, len(selected_calls) + 1):
            if step not in thought_by_step:
                call = selected_calls[step - 1]
                thought_by_step[step] = _task_oriented_thought(
                    call.get("tool_name", ""),
                    call.get("arguments", {}),
                    call.get("success", True),
                )

        # Post-process final response
        final_response = _postprocess_final_response(
            final_response=final_response,
            task_type=task_type,
            reference_answer=reference_answer,
            selected_calls=selected_calls,
            tool_results=tool_results,
        )
        if not final_response:
            final_response = _final_response_from_calls(
                task_type, reference_answer, tool_results
            )

        rewritten = [dict(m) for m in original_messages]

        step_idx = 1
        first_tool_assistant_written = False
        for msg in rewritten:
            if msg.get("role") != "assistant" or not msg.get("tool_calls"):
                continue

            call_count = len(msg.get("tool_calls") or [])
            thought_lines = []
            for _ in range(call_count):
                thought = thought_by_step.get(step_idx)
                if thought:
                    thought_lines.append(thought)
                step_idx += 1

            if not first_tool_assistant_written:
                if plan:
                    thought_lines.insert(0, plan)
                first_tool_assistant_written = True

            if thought_lines:
                msg["content"] = "\n".join(thought_lines)

        # Place final response after the last tool-use turn
        last_tool_turn_idx = -1
        for idx, msg in enumerate(rewritten):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                last_tool_turn_idx = idx

        # Clear any empty assistant placeholders before the last tool turn
        for idx, msg in enumerate(rewritten):
            if (
                msg.get("role") == "assistant"
                and not msg.get("tool_calls")
                and idx <= last_tool_turn_idx
            ):
                msg["content"] = ""

        final_written = False
        for idx in range(len(rewritten) - 1, -1, -1):
            msg = rewritten[idx]
            if (
                msg.get("role") == "assistant"
                and not msg.get("tool_calls")
                and idx > last_tool_turn_idx
            ):
                msg["content"] = final_response
                final_written = True
                break

        if not final_written and final_response:
            rewritten.append({"role": "assistant", "content": final_response})

        return rewritten

    async def _execute_harness_replay(
        self,
        *,
        problem: str,
        selected_calls: List[Dict[str, Any]],
        mcp_client: Any,
        maas_client: Any,
        model_config: Any,
        tools: List[Dict[str, Any]],
        task_type: str,
        language: str = "en",
        world_context: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """Execute selected tool sequence with model-driven harness.

        For each step, exposes only the next required tool to the model,
        calls the model to generate pre-action reasoning, validates the tool choice,
        and executes. For steps that failed in the original trajectory, exposes all
        tools to let the model adjust strategy naturally.

        Returns (messages, tool_results, final_response, forced_fallback_count).
        """
        system_prompt = _build_harness_system_prompt(language, world_context)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": problem},
        ]
        tool_results: List[str] = []
        forced_fallback_count = 0

        for step_idx, call in enumerate(selected_calls):
            expected_tool = call.get("tool_name", "")
            expected_args = call.get("arguments", {}) or {}
            is_failure_step = not call.get("success", True)

            if is_failure_step:
                available = tools
                enforce_match = False
            else:
                available = _filter_tools_by_name(tools, expected_tool)
                enforce_match = True

            step_msgs, step_result, forced = await self._execute_single_step(
                maas_client=maas_client,
                model_config=model_config,
                mcp_client=mcp_client,
                messages=list(messages),
                available_tools=available,
                expected_tool=expected_tool,
                expected_args=expected_args,
                enforce_match=enforce_match,
                retries=self.config.harness_max_retries_per_step,
            )
            messages.extend(step_msgs)
            tool_results.append(step_result)
            if forced:
                forced_fallback_count += 1

        final_response = await self._generate_final_response(
            maas_client=maas_client,
            model_config=model_config,
            messages=list(messages),
            task_type=task_type,
            language=language,
        )
        messages.append({"role": "assistant", "content": final_response})
        return messages, tool_results, final_response, forced_fallback_count

    async def _execute_single_step(
        self,
        *,
        maas_client: Any,
        model_config: Any,
        mcp_client: Any,
        messages: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]],
        expected_tool: str,
        expected_args: Dict[str, Any],
        enforce_match: bool,
        retries: int,
    ) -> tuple:
        """Execute one harness step: call model, validate tool choice, execute, retry if needed.

        Returns (messages_to_append, tool_result_string, forced_fallback: bool).
        forced_fallback is True when the model did not naturally pick the expected
        tool and we forced a template thought instead.
        """
        call_id = f"replay_call_{uuid.uuid4().hex[:8]}"

        openai_tools = _convert_tools_to_openai_format(available_tools) if available_tools else None

        for attempt in range(retries + 1):
            try:
                response = await maas_client.generate_completion(
                    messages=messages,
                    model_config=model_config,
                    tools=openai_tools,
                    temperature=0.7 if attempt > 0 else None,
                )
            except Exception as exc:
                if attempt >= retries:
                    raise
                logger.debug("Harness step LLM call failed (attempt %s/%s): %s", attempt + 1, retries + 1, exc)
                continue

            if not isinstance(response, dict):
                logger.warning("Harness LLM returned non-dict response: %s", type(response).__name__)
                continue
            tool_calls = response.get("tool_calls")
            reasoning = response.get("reasoning_content") or response.get("content") or ""

            if tool_calls and len(tool_calls) > 0:
                tc = tool_calls[0]
                model_tool = _get_tool_name_from_response(tc)
                model_args = _get_tool_args_from_response(tc)

                if enforce_match and model_tool != expected_tool:
                    # Model picked the wrong tool — prompt it to reconsider
                    messages.append(
                        {"role": "assistant", "content": reasoning or f"I'll try using {model_tool}."}
                    )
                    messages.append(
                        {"role": "user", "content": "Let me reconsider what tool to use for this task."}
                    )
                    if attempt >= retries:
                        # Force the expected tool — mark as forced BEFORE overwriting
                        forced = True
                        model_tool = expected_tool
                        model_args = expected_args
                        reasoning = _task_oriented_thought(expected_tool, expected_args, True)
                    else:
                        continue
                else:
                    forced = False

                # Choose actual args: use model's args unless we forced the expected tool
                if enforce_match:
                    actual_args = model_args if model_tool == expected_tool else expected_args
                else:
                    # Free mode (failure recovery): use the model's chosen tool + args
                    actual_args = model_args
                try:
                    result = await mcp_client.call_tool(model_tool, actual_args)
                except Exception as exc:
                    logger.warning("Harness tool call failed: tool=%s error=%s", model_tool, exc)
                    result = f"Tool execution error: {exc}"

                tool_result_text = _format_tool_result(result)
                assistant_msg = _build_assistant_tool_message(
                    model_tool, actual_args, reasoning, call_id
                )
                tool_msg = {"role": "tool", "tool_call_id": call_id, "content": tool_result_text}
                return [assistant_msg, tool_msg], tool_result_text, forced
            else:
                if attempt >= retries:
                    try:
                        result = await mcp_client.call_tool(expected_tool, expected_args)
                    except Exception as exc:
                        logger.warning("Harness fallback tool call failed: tool=%s error=%s", expected_tool, exc)
                        result = f"Tool execution error: {exc}"
                    tool_result_text = _format_tool_result(result)
                    fallback_thought = _task_oriented_thought(expected_tool, expected_args, True)
                    assistant_msg = _build_assistant_tool_message(
                        expected_tool, expected_args,
                        fallback_thought,
                        call_id,
                    )
                    tool_msg = {"role": "tool", "tool_call_id": call_id, "content": tool_result_text}
                    return [assistant_msg, tool_msg], tool_result_text, True
                messages.append(
                    {"role": "user", "content": "Please continue with the task using the available tools."}
                )
                continue

        # Unreachable under normal conditions; ultimate fallback.
        try:
            result = await mcp_client.call_tool(expected_tool, expected_args)
        except Exception as exc:
            logger.warning("Harness ultimate fallback tool call failed: tool=%s error=%s", expected_tool, exc)
            result = f"Tool execution error: {exc}"
        tool_result_text = _format_tool_result(result, max_chars=2000)
        fallback_thought = _task_oriented_thought(expected_tool, expected_args, True)
        assistant_msg = _build_assistant_tool_message(
            expected_tool, expected_args,
            fallback_thought,
            call_id,
        )
        tool_msg = {"role": "tool", "tool_call_id": call_id, "content": tool_result_text}
        return [assistant_msg, tool_msg], tool_result_text, True

    async def _generate_final_response(
        self,
        *,
        maas_client: Any,
        model_config: Any,
        messages: List[Dict[str, Any]],
        task_type: str,
        language: str,
    ) -> str:
        """Generate a natural-language final response from the model."""
        if language == "zh":
            response_prompt = "任务已完成。请根据以上的工具调用和结果，用自然语言总结完成的内容。"
        else:
            response_prompt = (
                "The task is complete. Based on the tool calls and results above, "
                "summarize what was accomplished in natural language. "
                "Be specific about what changed or what was found."
            )

        messages = list(messages)
        messages.append({"role": "user", "content": response_prompt})

        try:
            response = await maas_client.generate_completion(
                messages=messages,
                model_config=model_config,
                tools=None,
                temperature=0.7,
            )
            content = (response.get("content") or "").strip()
            if content:
                return content
        except Exception:
            logger.debug("Final response generation failed, using fallback", exc_info=True)

        if str(task_type).lower() == TaskType.RETRIEVAL.value:
            return "I have completed the retrieval task based on the observed results."
        return "Task completed successfully."


def _is_error_text(content: str) -> bool:
    """Check if a tool result string indicates an error.

    Handles both JSON-wrapped responses (FastMCP "isError" field or "error"
    key) and plain-text error strings like "Tool execution error: ...".
    """
    if not content:
        return False
    try:
        wrapper = json.loads(content)
        if isinstance(wrapper, dict):
            if wrapper.get("isError", False):
                return True
            if wrapper.get("error"):
                return True
        return False
    except (json.JSONDecodeError, TypeError):
        lowered = content.lower()
        return any(
            marker in lowered
            for marker in (
                "tool execution error", "no active episode",
                "traceback", "validation error",
            )
        )


def save_replay_artifacts(base_dir: Path, result: ReplaySynthesisResult, tools: List[Dict[str, Any]]) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    replay_dir = base_dir / f"replay_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    replay_dir.mkdir(parents=True, exist_ok=True)
    assert result.problem_spec is not None
    assert result.selection is not None
    _write_json(replay_dir / "problem.json", result.problem_spec.__dict__)
    _write_json(
        replay_dir / "trajectory.json",
        {
            "messages": result.messages,
            "tool_calls": result.selection.selected_calls,
            "num_steps": len(result.selection.selected_calls),
            "num_successful_tool_calls": sum(
                1 for r in result.tool_results if r and not _is_error_text(str(r))
            ),
            "status": "accepted" if result.accepted else "rejected",
        },
    )
    _write_json(
        replay_dir / "replay_context.json",
        {
            "selected_tool_sequence": result.selection.selected_calls,
            "dropped_calls": result.selection.dropped_calls,
            "evidence_summary": result.problem_spec.evidence_summary,
            "judge": result.problem_spec.judge,
        },
    )
    _write_json(replay_dir / "verification.json", result.verification)
    execution_meta = result.review_record.get("execution_meta", {}) if result.review_record else {}
    _write_json(
        replay_dir / "metadata.json",
        {
            "pipeline_mode": "trajs2data_replay_synthesis",
            "accepted": result.accepted,
            "rejected_reason": result.rejected_reason,
            **execution_meta,
        },
    )
    if result.review_record is not None:
        _write_json(replay_dir / "synthesized_review_records.json", [result.review_record])
    return replay_dir


def _is_mutation_tool(tool_name: str) -> bool:
    low = (tool_name or "").lower()
    return any(keyword in low for keyword in _MUTATION_KEYWORDS)


def _has_useful_failure_feedback(call: Dict[str, Any]) -> bool:
    feedback = f"{call.get('result') or ''} {call.get('error_message') or ''}".strip().lower()
    if not feedback:
        return False
    low_tool = str(call.get("tool_name") or "").lower()
    if "nonexistent" in low_tool or "unknown_tool" in low_tool:
        return False
    low_value_failures = (
        "invalid json",
        "schema validation",
        "missing required",
        "tool not found",
        "unknown tool",
        "parse error",
    )
    return not any(marker in feedback for marker in low_value_failures)


def _tool_family(tool_name: str) -> str:
    low = (tool_name or "").lower()
    for prefix in ("search_", "get_", "list_", "set_", "modify_", "add_", "remove_", "send_"):
        if low.startswith(prefix):
            return low.removeprefix(prefix)
    return low



def _focus(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("path", "query", "name", "target", "enabled", "status", "url"):
        if key in arguments:
            return f"{key}={arguments[key]}"
    return _safe_json_dumps(arguments, ensure_ascii=False)[:120]


def _extract_query_from_call(call: Dict[str, Any]) -> str:
    """Extract a search/query string from call arguments for keyword matching."""
    args = call.get("arguments", {}) if isinstance(call.get("arguments"), dict) else {}
    for key in ("query", "name", "path", "target", "search", "term", "recipient"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip().lower()
    return ""


def _keyword_overlap(a: str, b: str, min_length: int = 2) -> bool:
    """Check if two strings share at least one meaningful keyword."""
    if not a or not b:
        return False
    a_words = {w for w in a.lower().split() if len(w) >= min_length}
    b_words = {w for w in b.lower().split() if len(w) >= min_length}
    return bool(a_words & b_words)


def _has_meaningful_focus(args_focus: str, call_query: str) -> bool:
    """Check if args_focus or call_query has actual meaningful content (not just empty JSON)."""
    if call_query and call_query.strip():
        return True
    if args_focus and args_focus.strip() and args_focus.strip() != "{}":
        return True
    return False


def _evidence_summary(
    state_evidence: Optional[Dict[str, Any]], retrieval_spec: Optional[Any], selected_calls: List[Dict[str, Any]]
) -> str:
    if isinstance(state_evidence, dict) and state_evidence.get("summary"):
        return str(state_evidence.get("summary"))
    if retrieval_spec is not None:
        summary = getattr(retrieval_spec, "get_summary", None)
        if callable(summary):
            return str(summary())
        if isinstance(retrieval_spec, dict):
            return str(retrieval_spec.get("query_focus") or retrieval_spec.get("reference_answer") or retrieval_spec)
    return "; ".join(call.get("tool_name", "") for call in selected_calls)


# Argument value substrings that signal an exploration call, not a task-driven one.
# When ANY argument value contains one of these markers, the call is flagged as
# exploration and excluded from selected sequences.
_EXPLORATION_ARGUMENT_MARKERS: tuple[str, ...] = (
    "testing",
    "test message",
    "test content",
    "debug",
    "explore",
    "exploratory",
    "hello world",
    "foo bar",
    "lorem ipsum",
    "placeholder",
    "dummy",
    "sample text",
    "trial run",
    "just checking",
    "test test",
)


def _has_exploration_artifacts(arguments: Any) -> bool:
    """Check whether call arguments contain exploration markers.

    Returns True if any argument value (case-insensitive) contains a known
    exploration / debugging / placeholder string that signals the call was
    not driven by a real user task.
    """
    if not isinstance(arguments, dict):
        return False
    for val in arguments.values():
        sv = str(val).strip().lower()
        if not sv or sv in ("{}", "[]", "null", "none", "true", "false"):
            continue
        for marker in _EXPLORATION_ARGUMENT_MARKERS:
            if marker in sv:
                return True
    return False


# Common mutation verbs where tool_name = verb_noun and we can synthesize a
# natural-language instruction.  Each entry is (prefix, human_verb, needs_object).
# Ordered from most-specific to least-specific to avoid false matches (e.g.
# "search_" should not fire for mutation tools).
_MUTATION_VERB_PATTERNS: List[tuple[str, str, bool]] = [
    # Embodied / simulation worlds
    ("move_", "move", True),
    ("pickup_", "pick up", True),
    ("drop_", "drop", True),
    ("put_down_", "put down", True),
    ("open_", "open", True),
    ("close_", "close", True),
    ("activate_", "activate", True),
    ("deactivate_", "deactivate", True),
    ("enable_", "enable", True),
    ("disable_", "disable", True),
    ("toggle_", "toggle", True),
    ("pour_", "pour", False),
    ("mix_", "mix", True),
    ("eat_", "eat", True),
    ("focus_", "focus on", True),
    ("connect_", "connect", True),
    ("disconnect_", "disconnect", True),
    ("teleport_", "teleport", False),
    ("use_", "use", True),
    ("push_", "push", True),
    ("pull_", "pull", True),
    ("turn_on_", "turn on", True),
    ("turn_off_", "turn off", True),
    # Web UI automation
    ("click_", "click", True),
    ("type_", "type into", True),
    ("press_", "press", True),
    ("scroll_", "scroll in", True),
    ("drag_", "drag", True),
    ("hover_", "hover over", True),
    ("select_", "select", True),
    ("fill_", "fill in", True),
    ("submit_", "submit", True),
    ("clear_", "clear", True),
    # General mutation
    ("execute_", "execute", True),
    ("run_", "run", True),
    ("start_", "start", True),
    ("stop_", "stop", True),
    ("restart_", "restart", True),
    ("cancel_", "cancel", True),
    ("confirm_", "confirm", True),
    ("submit_", "submit", True),
    ("update_", "update", True),
    ("change_", "change", True),
    ("reset_", "reset", True),
    ("save_", "save", True),
    ("load_", "load", True),
    ("import_", "import", True),
    ("export_", "export", True),
    ("copy_", "copy", True),
    ("move_", "move", True),
    ("rename_", "rename", True),
    ("transfer_", "transfer", True),
    ("assign_", "assign", True),
    ("revoke_", "revoke", True),
    ("grant_", "grant", True),
    ("talk_", "talk to", True),
    ("read_", "read", True),
    ("inspect_", "inspect", True),
    ("check_", "check", True),
    ("lookup_", "look up", True),
    ("verify_", "verify", True),
    ("validate_", "validate", True),
    # Bare-verb tools (no underscore suffix) — e.g. discoveryworld
    ("move", "move", False),
]


def _mutation_problem_from_verb_noun_tool(
    tool: str, args: dict
) -> Optional[tuple[str, Dict[str, Any]]]:
    """Try to synthesize a mutation problem from a verb_noun-style tool name.

    Returns (problem, expected_outcome) or None if no pattern matches.
    """
    for prefix, human_verb, needs_object in _MUTATION_VERB_PATTERNS:
        if tool.startswith(prefix):
            rest = tool.removeprefix(prefix)
            if rest.startswith("_"):
                rest = rest[1:]
            noun = rest.replace("_", " ").strip()
            obj = args.get("name") or args.get("path") or args.get("object") or args.get("target") or args.get("element") or args.get("id") or ""
            value = args.get("value") or args.get("status") or args.get("enabled") or args.get("text") or args.get("content") or ""

            if needs_object and noun:
                detail = f" ({obj})" if obj else ""
                return (
                    f"Please {human_verb} the {noun}{detail}.",
                    {"state_hashes": {}},
                )
            elif not needs_object and noun:
                detail = f" with {value}" if value else ""
                return (
                    f"Please {human_verb} {noun}{detail}.",
                    {"state_hashes": {}},
                )
            elif value:
                return (
                    f"Please {human_verb} {value}.",
                    {"state_hashes": {}},
                )
            elif needs_object and obj:
                return (
                    f"Please {human_verb} the {obj}.",
                    {"state_hashes": {}},
                )
            else:
                return (
                    f"Please {human_verb} the {noun or 'target'}.",
                    {"state_hashes": {}},
                )

    # Broad fallback: any verb_noun tool not in the explicit list.
    # Split on first underscore, treat left as verb, right as noun target.
    if "_" in tool:
        verb, rest = tool.split("_", 1)
        noun = rest.replace("_", " ").strip()
        obj = args.get("name") or args.get("path") or args.get("object") or args.get("target") or args.get("element") or args.get("id") or ""
        detail = f" ({obj})" if obj else ""
        return (
            f"Please {verb} the {noun}{detail}.",
            {"state_hashes": {}},
        )

    return None


def _mutation_problem_from_selected_calls(
    selected_calls: List[Dict[str, Any]], state_evidence: Optional[Dict[str, Any]]
) -> tuple[str, Dict[str, Any]]:
    for call in selected_calls:
        tool = call.get("tool_name", "")
        args = call.get("arguments", {}) if isinstance(call.get("arguments"), dict) else {}
        if tool == "set_wifi_status":
            value = _bool_status(args.get("enabled", args.get("status")))
            return (
                f"Please set Wi-Fi to {value}.",
                {"wifi_status": value, "state_hashes": {"settings_hash": None}},
            )
        if tool in _STATUS_TO_SET_TOOL.values() or tool.startswith("set_"):
            setting = tool.removeprefix("set_").replace("_", " ")
            value = _bool_status(args.get("enabled", args.get("status", args.get("value"))))
            return (
                f"Please set {setting} to {value}.",
                {setting.replace(" ", "_"): value, "state_hashes": {"settings_hash": None}},
            )
        if tool.startswith("add_"):
            target = tool.removeprefix("add_").replace("_", " ")
            name = args.get("name") or args.get("content") or args.get("phone_number") or ""
            detail = f" ({name})" if name else ""
            return (
                f"Please add a {target}{detail}.",
                {target.replace(" ", "_"): name, "state_hashes": {}},
            )
        if tool.startswith("modify_"):
            target = tool.removeprefix("modify_").replace("_", " ")
            name = args.get("content") or args.get("name") or args.get("person_id") or ""
            detail = f" ({name})" if name else ""
            return (
                f"Please modify the {target}{detail}.",
                {target.replace(" ", "_"): name, "state_hashes": {}},
            )
        if tool.startswith("send_"):
            target = tool.removeprefix("send_").replace("_", " ")
            recipient = args.get("phone_number") or args.get("recipient") or ""
            return (
                f"Please send a {target} to {recipient}." if recipient else f"Please send a {target}.",
                {"state_hashes": {}},
            )
        if tool.startswith("write") or "write_file" in tool:
            path = args.get("path") or args.get("file") or "the target file"
            return (
                f"Please update {path} with the requested content.",
                {"path": path, "state_hashes": {}},
            )
        if tool.startswith("create"):
            name = args.get("path") or args.get("name") or "the requested resource"
            return (
                f"Please create {name}.",
                {"target": name, "state_hashes": {}},
            )
        if any(k in tool for k in ("delete", "remove")):
            name = args.get("path") or args.get("name") or "the requested resource"
            return (
                f"Please remove {name}.",
                {"target": name, "state_hashes": {}},
            )
        # Generic verb_noun mutation patterns (scienceworld, discoveryworld, webshop, miniwob, etc.)
        problem = _mutation_problem_from_verb_noun_tool(tool, args)
        if problem is not None:
            return problem
    summary = str((state_evidence or {}).get("summary") or "the observed state change")
    return (
        f"Please reproduce this requested change: {summary}.",
        {"summary": summary, "state_hashes": {}},
    )


def _retrieval_problem_from_evidence(
    retrieval_spec: Optional[Any], selected_calls: List[Dict[str, Any]]) -> tuple[str, Dict[str, Any]]:
    query_focus = "the requested information"
    reference_answer = ""
    if selected_calls:
        call = selected_calls[-1]
        query_focus = _retrieval_focus_from_call(call)
        reference_answer = str(call.get("result") or "")[:500]
    elif retrieval_spec is not None:
        if isinstance(retrieval_spec, dict):
            query_focus = str(retrieval_spec.get("query_focus") or query_focus)
            reference_answer = str(retrieval_spec.get("reference_answer") or "")
        else:
            query_focus = str(getattr(retrieval_spec, "query_focus", query_focus))
            reference_answer = str(getattr(retrieval_spec, "reference_answer", ""))
    return f"Please find and report {query_focus}.", {"reference_answer": reference_answer}


def _retrieval_focus_from_call(call: Dict[str, Any]) -> str:
    tool = str(call.get("tool_name") or "")
    args = call.get("arguments", {}) if isinstance(call.get("arguments"), dict) else {}
    query = str(args.get("query") or "").strip()
    path = str(args.get("path") or "").strip()
    if tool.startswith("search_"):
        target = tool.removeprefix("search_").replace("_", " ")
        return f"{target} matching {query}" if query else f"all matching {target}"
    if tool.startswith("get_"):
        target = tool.removeprefix("get_").replace("_", " ")
        return target
    if tool.startswith("list_"):
        target = tool.removeprefix("list_").replace("_", " ")
        return target
    if query:
        return query
    if path:
        return path
    return "the requested information"



def _judge_problem_utility(problem: str, task_type: str, evidence_summary: str) -> Dict[str, Any]:
    lowered = (problem or "").lower()
    bad_markers = (
        "what am i supposed to do",
        "current task",
        "what task",
        "allowed to access",
        "what tools",
        "which tools",
    )
    if any(marker in lowered for marker in bad_markers):
        return {"consistent": False, "utility": "reject", "reason": "meta_or_state_query"}
    if not evidence_summary:
        return {"consistent": False, "utility": "reject", "reason": "missing_evidence"}
    if "please reproduce this requested change" in lowered:
        return {"consistent": False, "utility": "reject", "reason": "fallback_problem_no_rule_match"}
    if "s0=" in lowered and "s1=" in lowered and "hash" in lowered:
        return {"consistent": False, "utility": "reject", "reason": "fallback_problem_contains_raw_state_hashes"}
    return {"consistent": True, "utility": "high", "reason": "evidence_aligned_action_request"}


def _bool_status(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    text = str(value).strip().lower()
    if text in {"false", "0", "off", "disabled", "disable"}:
        return "off"
    if text in {"true", "1", "on", "enabled", "enable"}:
        return "on"
    return text or "the requested value"


def _task_oriented_thought(tool_name: str, arguments: Dict[str, Any], success: bool = True) -> str:
    low = tool_name.lower()
    if not success:
        return f"I should try this task-relevant lookup with {tool_name} and use the result to adjust if needed."
    # Extract argument context for richer thought templates
    name = str(arguments.get("name") or arguments.get("query") or arguments.get("path") or arguments.get("target") or "")
    recipient = str(arguments.get("recipient") or arguments.get("phone_number") or "")
    enabled = arguments.get("enabled")
    status_val = arguments.get("status")
    if low.startswith("set_"):
        setting = tool_name.removeprefix("set_").replace("_", " ")
        if enabled is not None:
            state = "on" if enabled else "off"
            return f"I need to turn {state} {setting} as the user requested."
        elif status_val is not None:
            return f"I need to set {setting} to {status_val} as the user requested."
        return f"I need to apply the requested {setting} change."
    if low.startswith("search_"):
        target = tool_name.removeprefix("search_").replace("_", " ")
        if name:
            return f"I need to search {target} for '{name}' to fulfill the user's request."
        return f"I need to look up the relevant {target} information."
    if low.startswith("get_"):
        target = tool_name.removeprefix("get_").replace("_", " ")
        if name:
            return f"I need to retrieve {target} details for '{name}'."
        return f"I need to retrieve the {target} information the user asked about."
    if low.startswith("list_"):
        target = tool_name.removeprefix("list_").replace("_", " ")
        if name:
            return f"I need to list {target} in '{name}' as the user requested."
        return f"I need to list the {target} the user wants to see."
    if low.startswith("send_"):
        target = tool_name.removeprefix("send_").replace("_", " ")
        if recipient:
            return f"I need to send a {target} to {recipient}."
        if name:
            return f"I need to send the {target}: {name}."
        return f"I need to send the {target} the user requested."
    if "write" in low or "create" in low:
        if name:
            return f"I need to create '{name}' as the user specified."
        return f"I need to create the requested resource."
    if "delete" in low or "remove" in low:
        if name:
            return f"I need to remove '{name}' as the user asked."
        return f"I need to remove the requested target."
    if low.startswith("add_"):
        target = tool_name.removeprefix("add_").replace("_", " ")
        if name:
            return f"I need to add {target}: {name}."
        return f"I need to add the requested {target}."
    if low.startswith("modify_"):
        target = tool_name.removeprefix("modify_").replace("_", " ")
        if name:
            return f"I need to modify {target} '{name}' as the user requested."
        return f"I need to modify the {target}."
    if name:
        return f"I need to use {tool_name} on '{name}' to complete the user's task."
    return f"I need to perform the next task action using {tool_name}."


def _final_response(problem_spec: ReplayProblemSpec, selected_calls: List[Dict[str, Any]], tool_results: List[str]) -> str:
    if problem_spec.task_type == TaskType.RETRIEVAL.value and problem_spec.reference_answer:
        return problem_spec.reference_answer
    if tool_results:
        last = tool_results[-1]
        inner = _extract_inner_result(last)
        if inner and len(inner) < 500:
            return f"Done: {inner}"
        # Before fabricating success, check if the result indicates an error
        if _is_error_text(last):
            return "The task could not be completed because the tool encountered an error."
        return f"Done. The task was completed based on the tool results: {inner[:200] if inner else 'success'}"
    return "Done. The requested task has been completed."


def _extract_inner_result(raw: str) -> str:
    """Extract the inner result from a FastMCP wrapper response."""
    if not raw:
        return ""
    try:
        data = json.loads(raw)
        sc = data.get("structuredContent", {})
        if isinstance(sc, dict):
            inner = sc.get("result", "")
            if isinstance(inner, str):
                try:
                    inner_data = json.loads(inner)
                    if isinstance(inner_data, dict):
                        status = inner_data.get("status", "")
                        parts = [f"{k}: {v}" for k, v in inner_data.items() if k != "status"]
                        return f"{status}: " + ", ".join(parts) if parts else status
                    return inner
                except (json.JSONDecodeError, TypeError):
                    return inner
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return raw[:300]


def _format_tool_result(result: Any, *, max_chars: Optional[int] = None) -> str:
    text = result if isinstance(result, str) else ""
    if not isinstance(result, str):
        try:
            text = json.dumps(result, ensure_ascii=False)
        except Exception:
            text = str(result)
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + f"\n... [truncated, {len(text) - max_chars} more chars]"
    return text


def _state_hash_view(state: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in state.items() if key.endswith("_hash")}


def _verify_expected_hash_subset(
    replay_s1: Any, expected_outcome: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    if not isinstance(replay_s1, dict) or not isinstance(expected_outcome, dict):
        return None
    expected_hashes = expected_outcome.get("state_hashes")
    if not isinstance(expected_hashes, dict):
        return None
    if not expected_hashes:
        # Empty dict: caller explicitly wants no hash verification.
        return {"verified": True, "strategy": "expected_outcome_hash_subset_skip", "reason": "no hashes specified"}

    observed = {}
    for key, expected_val in expected_hashes.items():
        observed[key] = replay_s1.get(key)
        if expected_val is None:
            # None means "key must exist in replay_s1" (any value ok).
            if observed[key] is None:
                return {
                    "verified": False,
                    "strategy": "expected_outcome_hash_subset",
                    "expected": expected_hashes,
                    "observed": observed,
                    "reason": f"missing key: {key}",
                }
        elif observed[key] != expected_val:
            return {
                "verified": False,
                "strategy": "expected_outcome_hash_subset",
                "expected": expected_hashes,
                "observed": observed,
                "reason": f"hash mismatch for {key}",
            }

    return {
        "verified": True,
        "strategy": "expected_outcome_hash_subset",
        "expected": expected_hashes,
        "observed": observed,
    }



# ---------------------------------------------------------------------------
# Harness helper functions
# ---------------------------------------------------------------------------

def _build_harness_system_prompt(
    language: str,
    world_context: Optional[Dict[str, Any]] = None,
) -> str:
    """System prompt for harness-driven replay.

    Injects operator_role from world_context so the model adopts the correct
    domain persona (database engineer, virtual assistant, etc.).

    CRITICAL: Must NOT mention tool sequences, harnesses, or pre-selected steps.
    """
    operator_role = ""
    if world_context:
        operator_role = str(world_context.get("operator_role", "") or "").strip()

    if language == "zh":
        prefix = ""
        if operator_role:
            prefix = f"你的角色是{operator_role}。"
        return (
            f"{prefix}"
            "你是一个直接使用工具完成用户请求的助手。"
            "仔细理解用户的任务，然后使用可用的工具逐步完成。"
            "在每次操作前，说明你为什么选择这个工具以及期望的结果。"
            "当任务完成时，总结你所完成的内容。"
        )
    else:
        prefix = ""
        if operator_role:
            prefix = f"Your role is: {operator_role}. "
        return (
            f"{prefix}"
            "You are a helpful assistant that uses tools directly to complete user tasks. "
            "Carefully understand the user's request, then use available tools to complete it step by step. "
            "Before each action, explain why you chose this tool and what result you expect. "
            "When the task is complete, summarize what was accomplished."
        )


def _filter_tools_by_name(tools: List[Dict[str, Any]], name: str) -> List[Dict[str, Any]]:
    """Filter tool list to only include the tool with the given name."""
    result = []
    for t in tools:
        t_name = t.get("name") or t.get("function", {}).get("name", "")
        if t_name == name:
            result.append(t)
    return result


def _convert_tools_to_openai_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert FastMCP-format tool definitions to OpenAI function-calling format.

    FastMCP format: {name, description, inputSchema: {properties, required, type}}
    OpenAI format: {type: "function", function: {name, description, parameters: {...}}}
    Already-converted tools pass through unchanged.
    """
    converted = []
    for t in tools:
        if "function" in t:
            converted.append(t)
            continue
        name = t.get("name", "")
        description = t.get("description", "")
        params = t.get("inputSchema") or {}
        if not isinstance(params, dict):
            params = {}
        converted.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": params.get("type", "object"),
                    "properties": params.get("properties", {}),
                    "required": params.get("required", []),
                },
            },
        })
    return converted


def _get_tool_name_from_response(tc: Any) -> str:
    """Extract tool name from a model response tool call object."""
    if hasattr(tc, "function") and hasattr(tc.function, "name"):
        return tc.function.name
    if isinstance(tc, dict):
        func = tc.get("function", {})
        return func.get("name", "")
    return ""


def _get_tool_args_from_response(tc: Any) -> Dict[str, Any]:
    """Extract and parse tool arguments from a model response tool call object."""
    raw = ""
    if hasattr(tc, "function") and hasattr(tc.function, "arguments"):
        raw = tc.function.arguments
    elif isinstance(tc, dict):
        func = tc.get("function", {})
        raw = func.get("arguments", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _build_assistant_tool_message(
    tool_name: str, args: Dict[str, Any], thought: str, call_id: str,
) -> Dict[str, Any]:
    """Build an assistant message with a single tool call."""
    return {
        "role": "assistant",
        "content": thought,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": _safe_json_dumps(args, ensure_ascii=False),
                },
            }
        ],
    }


def _build_tool_error_message(call_id: str, error_text: str) -> Dict[str, Any]:
    """Build a tool response message containing an error."""
    return {"role": "tool", "tool_call_id": call_id, "content": error_text}


# ---------------------------------------------------------------------------
# Polish and judge helper functions
# ---------------------------------------------------------------------------

def _format_world_context(wc: Optional[Dict[str, Any]]) -> str:
    """Compact world context for prompt injection."""
    if not wc:
        return ""
    parts = []
    for k, v in wc.items():
        if v:
            parts.append(f"- {k}: {v}")
    return "\n".join(parts) if parts else ""


def _sanitize_deepseek_tokens(text: str, *, clean_garbled: bool = True) -> str:
    """Remove DeepSeek special tokens and (optionally) garbled artifacts that leak into output."""
    if not text:
        return text
    # DeepSeek V4 special tokens
    tokens = (
        "<｜begin▁of▁sentence｜>",
        "<｜end▁of▁sentence｜>",
        "<｜begin▁of▁thought｜>",
        "<｜end▁of▁thought｜>",
        "<｜begin▁of▁answer｜>",
        "<｜end▁of▁answer｜>",
        " <｜begin▁of▁sentence｜>",
        "<｜begin▁of▁sentence｜> ",
    )
    for token in tokens:
        text = text.replace(token, "")
    if clean_garbled:
        text = _clean_garbled_artifacts(text)
    return text.strip()


def _clean_garbled_artifacts(text: str) -> str:
    """Remove common LLM garbled artifacts: Chinese chars, orphaned digits in words, stray punctuation."""
    if not text:
        return text
    # Remove Chinese characters (CJK Unified Ideographs: U+4E00–U+9FFF,
    # CJK Extension A: U+3400–U+4DBF, CJK Compatibility: U+F900–U+FAFF)
    cleaned: List[str] = []
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0xF900 <= cp <= 0xFAFF):
            continue
        # Replace fullwidth Chinese punctuation with ASCII equivalents
        if cp == 0xFF0C:  # ，
            cleaned.append(",")
        elif cp == 0x3002:  # 。
            cleaned.append(".")
        elif cp == 0xFF1A:  # ：
            cleaned.append(":")
        elif cp == 0xFF1B:  # ；
            cleaned.append(";")
        elif cp == 0xFF08:  # （
            cleaned.append("(")
        elif cp == 0xFF09:  # ）
            cleaned.append(")")
        elif 0xFF00 <= cp <= 0xFFEF:  # Other fullwidth forms → skip
            continue
        elif 0x3000 <= cp <= 0x303F:  # CJK Symbols/Punctuation → skip
            continue
        else:
            cleaned.append(ch)
    text = "".join(cleaned)

    # Fix orphaned digits fused into words: "any04" → "any", "Also,12233" → "Also,"
    import re as _re
    text = _re.sub(r'\b([a-zA-Z]+)\d+\b', r'\1', text)
    # Remove stray 2+ digit numbers that are likely artifacts in English text
    # (but keep phone numbers and timestamps which have context)
    text = _re.sub(r',\s*\d{4,}', ', ', text)

    return text


def _contains_chinese(text: str) -> bool:
    """Check if text contains Chinese (CJK) characters."""
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0xF900 <= cp <= 0xFAFF):
            return True
    return False


def _parse_json_from_response(resp: Any) -> Any:
    """Parse JSON from a model text response, handling markdown fences and special tokens."""
    if isinstance(resp, dict):
        return resp
    if not isinstance(resp, str):
        return None
    text = _sanitize_deepseek_tokens(resp)
    # Remove markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _postprocess_final_response(
    *,
    final_response: str,
    task_type: str,
    reference_answer: str,
    selected_calls: List[Dict[str, Any]],
    tool_results: List[str],
) -> str:
    """Ensure final response is grounded in actual tool outputs."""
    if final_response and final_response.strip():
        return final_response.strip()
    return _final_response_from_calls(task_type, reference_answer, tool_results)


def _final_response_from_calls(
    task_type: str,
    reference_answer: str,
    tool_results: List[str],
) -> str:
    """Build a fallback final response from tool outputs."""
    if str(task_type).lower() == "retrieval" and reference_answer:
        return reference_answer
    if tool_results:
        last = tool_results[-1]
        inner = _extract_inner_result(last)
        if inner and len(inner) < 500:
            return f"Done: {inner}"
        return f"Task completed based on the tool results: {inner[:200] if inner else 'success'}"
    return "Task completed successfully."


async def _judge_replay_trajectory(
    *,
    maas_client: Any,
    judge_model_config: Any,
    problem: str,
    task_type: str,
    messages: List[Dict[str, Any]],
    selected_calls: List[Dict[str, Any]],
    reference_answer: str = "",
    world_context: Optional[Dict[str, Any]] = None,
    score_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Run dual-judge (hard + soft) on a replay trajectory.

    Returns a dict with hard_judge_pass, soft_judge_pass, soft_judge_issues,
    quality_score, quality_tier.
    """
    from prompts.synthesis_judge import (
        JUDGE_TRAJECTORY_HARD_SYSTEM_PROMPT,
        JUDGE_TRAJECTORY_HARD_USER_TEMPLATE,
        JUDGE_TRAJECTORY_SOFT_SYSTEM_PROMPT,
        JUDGE_TRAJECTORY_SOFT_USER_TEMPLATE,
    )

    wc_text = _format_world_context(world_context)
    trajectory_text = _trajectory_to_text(messages)
    # Soft judge gets a style-focused view: assistant thoughts with result summaries,
    # de-emphasizing raw tool outputs to focus on framing quality.
    trajectory_style_text = _trajectory_to_style_text(messages)
    required_tool_steps = len(selected_calls)

    # ── Hard judge (full trajectory for factual verification) ──
    hard_user = JUDGE_TRAJECTORY_HARD_USER_TEMPLATE.format(
        world_context=wc_text,
        task_type=task_type,
        problem=problem,
        required_tool_steps=required_tool_steps,
        require_final_answer="true",
        reference_answer=reference_answer or "N/A",
        trajectory_full=trajectory_text,
    )

    # ── Soft judge (style-focused trajectory view for reasoning quality) ──
    soft_user = JUDGE_TRAJECTORY_SOFT_USER_TEMPLATE.format(
        world_context=wc_text,
        task_type=task_type,
        problem=problem,
        require_plan="false",
        required_tool_steps=required_tool_steps,
        require_final_answer="true",
        reference_answer=reference_answer or "N/A",
        trajectory_full=trajectory_style_text,
    )

    # Run Hard and Soft judges in parallel — they are independent LLM calls.
    async def _run_hard_judge() -> tuple[bool, str]:
        try:
            resp = await maas_client.generate_text(
                hard_user,
                judge_model_config,
                system_prompt=JUDGE_TRAJECTORY_HARD_SYSTEM_PROMPT,
            )
            payload = _parse_json_from_response(resp)
            if isinstance(payload, dict):
                return (
                    bool(payload.get("consistent", False)),
                    _sanitize_deepseek_tokens(str(payload.get("reason", "")), clean_garbled=True),
                )
            return (False, "hard_judge_unexpected_response")
        except Exception:
            logger.warning("Hard judge call failed — rejecting trajectory as fail-safe", exc_info=True)
            return (False, "hard_judge_exception")

    async def _run_soft_judge() -> tuple[bool, str, list[str]]:
        try:
            resp = await maas_client.generate_text(
                soft_user,
                judge_model_config,
                system_prompt=JUDGE_TRAJECTORY_SOFT_SYSTEM_PROMPT,
            )
            payload = _parse_json_from_response(resp)
            if isinstance(payload, dict):
                return (
                    bool(payload.get("realistic", False)),
                    str(payload.get("severity", "")).lower(),
                    [
                        _sanitize_deepseek_tokens(str(s), clean_garbled=True)
                        for s in (payload.get("issues", []) or [])
                    ],
                )
            return (False, "major", ["soft_judge_unexpected_response"])
        except Exception:
            logger.warning("Soft judge call failed", exc_info=True)
            return (False, "major", ["soft_judge_exception"])

    (hard_pass, hard_reason), (soft_pass, soft_severity, soft_issues) = (
        await asyncio.gather(_run_hard_judge(), _run_soft_judge())
    )

    # ── Compute quality score ──
    weights = score_weights or {}
    hard_weight = float(weights.get("hard", 0.70))
    soft_weight = float(weights.get("soft", 0.20))
    dual_bonus = float(weights.get("dual_bonus", 0.10))
    threshold_high = float(weights.get("threshold_high", 0.85))
    threshold_acceptable = float(weights.get("threshold_acceptable", 0.70))

    score = hard_weight if hard_pass else 0.0
    if soft_pass:
        score += soft_weight
    if hard_pass and soft_pass:
        score += dual_bonus
    score = max(0.0, min(1.0, round(score, 4)))

    if score >= threshold_high:
        quality_tier = "high_quality"
    elif score >= threshold_acceptable:
        quality_tier = "acceptable"
    else:
        quality_tier = "reject"

    # Soft judge major severity override: systemic quality failures (contextless
    # steps, verbatim repetition, raw payload dumps, failure unawareness, etc.)
    # degrade training data regardless of factual correctness.  Force-reject.
    if quality_tier == "acceptable" and soft_severity == "major":
        quality_tier = "reject"
        score = min(score, threshold_acceptable - 0.01)

    return {
        "hard_judge_pass": hard_pass,
        "hard_judge_reason": hard_reason,
        "soft_judge_pass": soft_pass,
        "soft_judge_issues": soft_issues,
        "soft_judge_severity": soft_severity,
        "quality_score": round(score, 4),
        "quality_tier": quality_tier,
        "selected_for_training": quality_tier != "reject",
    }


def _trajectory_to_text(messages: List[Dict[str, Any]]) -> str:
    """Convert message list to compact text for judge prompts."""
    lines = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        tool_call_id = msg.get("tool_call_id", "")

        if role == "system":
            lines.append(f"[System] {content}")
        elif role == "user":
            lines.append(f"[User] {content}")
        elif role == "assistant":
            if tool_calls:
                tc_names = [
                    tc.get("function", {}).get("name", "?")
                    for tc in tool_calls
                ]
                lines.append(f"[Assistant → calls {', '.join(tc_names)}] {content}")
            else:
                lines.append(f"[Assistant] {content}")
        elif role == "tool":
            content_preview = (content or "")[:200]
            lines.append(f"[Tool result: {tool_call_id}] {content_preview}")
    return "\n".join(lines)


def _trajectory_to_style_text(messages: List[Dict[str, Any]]) -> str:
    """Convert message list to a style-focused text for the soft judge.

    Unlike _trajectory_to_text (which includes raw tool results for factual verification),
    this formatter emphasizes assistant reasoning flow and collapses tool outputs to
    short status indicators. This helps the soft judge focus on reasoning quality
    and coherence rather than being distracted by raw result payloads.
    """
    lines = []
    step_idx = 0
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        tool_call_id = msg.get("tool_call_id", "")

        if role == "system":
            lines.append(f"[System] {content}")
        elif role == "user":
            lines.append(f"[User Task] {content}")
        elif role == "assistant":
            if tool_calls:
                tc_names = [
                    tc.get("function", {}).get("name", "?")
                    for tc in tool_calls
                ]
                tc_args = []
                for tc in tool_calls:
                    args = tc.get("function", {}).get("arguments", "")
                    if args:
                        try:
                            args_dict = json.loads(args) if isinstance(args, str) else args
                            focus = _focus(args_dict)
                            tc_args.append(focus if focus else "...")
                        except (json.JSONDecodeError, TypeError):
                            tc_args.append("...")
                lines.append(
                    f"[Step {step_idx + 1}: {', '.join(tc_names)}"
                    f"({' | '.join(tc_args) if tc_args else ''})] {content}"
                )
            else:
                lines.append(f"[Final Answer] {content}")
        elif role == "tool":
            step_idx += 1
            # Collapse tool results: just note success/failure.
            # Parse FastMCP wrapper to get the actual isError flag — do NOT
            # use substring matching because "isError" field name itself
            # contains "error" and would mark every call as FAILED.
            has_error = _parse_is_error(content)
            lines.append(
                f"  → {'✗ FAILED' if has_error else '✓ OK'} (step {step_idx})"
            )
    return "\n".join(lines)


def _parse_is_error(content: str) -> bool:
    """Check if a tool response is actually an error.

    Handles both FastMCP JSON wrapper ("isError" field / "error" key) and
    plain-text error strings like "Tool execution error: ...".
    """
    return _is_error_text(content)


def _write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
