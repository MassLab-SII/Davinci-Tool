"""MCP-Trajs2Data: Trajectory-to-Problem Data Synthesis Engine.

This pipeline implements the Traj→Problem paradigm for generating high-quality
training data for LLM tool-calling capabilities. Instead of the traditional
Problem→Trajectory approach, this engine:

1. Lets the model explore freely in a controlled environment (S0)
2. Collects the trajectory of successful tool calls
3. Synthesizes a natural language problem description from the trajectory

This approach ensures data validity (trajectory is ground truth) and supports:
- Curriculum learning via configurable target_n (successful tool call count)
- Dual-mode synthesis (mutation vs retrieval)
- Phase-based tool curriculum with coverage optimization
"""

import asyncio
import logging
import shutil
import random
import copy
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_collection.tool_metadata import ToolMetadataResolver
from data_collection.utils.config import load_config
from data_collection.mcp_servers.server_factory import create_mcp_server
from data_collection.mcp_servers.server_manager import MCPServerManager
from data_collection.executable_worlds.env_pool import ExecutableWorldEnvPool
from data_collection.executable_worlds.compose_runner import ComposeRunner
from data_collection.executable_worlds.session_headers import build_world_session_headers
from data_collection.maas_client import MaaSClient
from data_collection.utils.storage import Storage
from data_collection.dedup.semantic_deduplicator import (
    SemanticDeduplicator,
    OpenAICompatibleEmbedding,
)

# Trajs2Data core imports
from data_collection.state.filesystem_snapshot import (
    snapshot_filesystem,
    diff_snapshots,
)
from data_collection.state.checkpoint_manager import CheckpointManager
from data_collection.trajs2data_collector import (
    Trajs2DataCollector,
    build_exploration_system_prompt,
    EpisodeStatus,
)
from data_collection.problem_synthesizer import (
    rewrite_to_problem_json,
    rewrite_retrieval_to_problem_json,
    determine_task_type,
    TaskType,
    build_retrieval_spec,
    rewrite_trajectory_thoughts,
    apply_hard_filters,
    apply_soft_filters,
)
from data_collection.sampling import CoverageTracker, StageAwareSampler, SamplingResult
from data_collection.efficiency_monitor import EfficiencyMonitor
from data_collection.exploration_state import ExplorationStateRecorder
from data_collection.experience import ExperienceManager
from data_collection.experience.experience_manager import create_experience_manager
from data_collection.state.filesystem_benchmark_init import (
    FilesystemBenchmarkRepository,
)
from data_collection.quality.anchor_tracking import build_anchor_usage_metadata
from data_collection.worlds.context import build_state_evidence, build_world_context
from data_collection.replay_synthesis import (
    ReplaySynthesisConfig,
    ReplaySynthesisRunner,
    restore_admin_replay_s0,
)


def _get_server_metadata(config, server_name: str, selected_env=None) -> dict:
    """Resolve metadata for a server from config and optional executable world."""
    if selected_env is not None:
        metadata = {
            "output_namespace": selected_env.name,
            "prompt_domain": selected_env.name,
            "tool_metadata": {},
        }
        env_tool_metadata = getattr(selected_env, "tool_metadata", None)
        if isinstance(env_tool_metadata, dict):
            metadata["tool_metadata"] = env_tool_metadata
        env_prompt_domain = getattr(selected_env, "prompt_domain", None)
        if env_prompt_domain:
            metadata["prompt_domain"] = env_prompt_domain
        env_output_namespace = getattr(selected_env, "output_namespace", None)
        if env_output_namespace:
            metadata["output_namespace"] = env_output_namespace
        env_world_context = getattr(selected_env, "world_context", None)
        if isinstance(env_world_context, dict) and env_world_context:
            metadata["world_context"] = env_world_context
        return metadata

    if server_name in getattr(config, "stdio_mcp_servers", {}):
        return getattr(config.stdio_mcp_servers[server_name], "metadata", {}) or {}
    if server_name in getattr(config, "http_mcp_servers", {}):
        return getattr(config.http_mcp_servers[server_name], "metadata", {}) or {}
    return {}


def _build_episode_world_context(task_config, selected_env=None) -> dict:
    """Merge task-level and selected executable-world context."""
    context = {}
    task_context = getattr(task_config, "world_context", None)
    if isinstance(task_context, dict):
        context.update(task_context)
    elif task_context:
        context["description"] = str(task_context)

    if selected_env is not None:
        context.setdefault("selected_env", getattr(selected_env, "name", None))
        env_context = getattr(selected_env, "world_context", None)
        if isinstance(env_context, dict):
            context.update(env_context)
        elif env_context:
            context["selected_env_description"] = str(env_context)

    return context


def _safe_tool_names_from_trajectory(trajectory) -> List[str]:
    """Extract successful tool names from a trajectory-like object."""
    if trajectory is None:
        return []
    tool_calls = getattr(trajectory, "tool_calls", None)
    if tool_calls is None and isinstance(trajectory, dict):
        tool_calls = trajectory.get("tool_calls", [])
    names: List[str] = []
    for call in tool_calls or []:
        if isinstance(call, dict):
            if call.get("success", True):
                name = call.get("tool_name") or call.get("tool")
                if name:
                    names.append(str(name))
        else:
            if getattr(call, "success", True):
                name = getattr(call, "tool_name", None)
                if name:
                    names.append(str(name))
    return names


_MUTATION_TOOL_NAMES = {
    # Filesystem
    "write_file",
    "edit_file",
    "create_directory",
    "move_file",
    # GitHub
    "create_issue",
    "add_issue_comment",
    "update_issue",
    "create_label",
    "update_label",
    "update_pull_request",
    "add_pull_request_review_comment",
    "merge_pull_request",
    "create_or_update_file",
    "create_branch",
    "create_pull_request",
    "create_release",
    # Postgres
    "execute_sql",
    # Playwright/browser state actions
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_select_option",
    "browser_file_upload",
    "browser_navigate",
}

_READ_TOOL_PREFIXES = (
    "read_",
    "list_",
    "search_",
    "get_",
    "find_",
    "browser_snapshot",
    "browser_get",
    "browser_take",
    "browser_evaluate",
    "browser_wait",
    "query",
    "describe",
    "explain",
)

_ARTIFACT_WRITE_TOOL_NAMES = {
    "write_file",
    "edit_file",
    "create_or_update_file",
    "create_issue",
    "add_issue_comment",
    "create_label",
    "create_branch",
    "create_pull_request",
    "create_release",
    "execute_sql",
}


def _tool_call_field(call: Any, field: str, default: Any = None) -> Any:
    """Read a field from dict- or dataclass-style tool call records."""
    if isinstance(call, dict):
        return call.get(field, default)
    return getattr(call, field, default)


def _tool_call_name(call: Any) -> str:
    return str(
        _tool_call_field(call, "tool_name")
        or _tool_call_field(call, "name")
        or _tool_call_field(call, "tool")
        or ""
    )


def _tool_call_success(call: Any) -> bool:
    return bool(_tool_call_field(call, "success", True))


def _is_read_like_tool(tool_name: str) -> bool:
    return any(tool_name.startswith(prefix) for prefix in _READ_TOOL_PREFIXES)


def _ordered_unique_strings(values: List[str]) -> List[str]:
    seen = set()
    ordered = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _build_quality_signals(
    *,
    trajectory,
    state_evidence: Optional[Dict[str, Any]],
    anchor_usage: Optional[Dict[str, Any]],
    sampling_result: Optional[SamplingResult],
    target_n: Optional[int],
    checkpoint_stats: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build observational metadata for downstream filtering and analysis."""
    tool_calls = getattr(trajectory, "tool_calls", None) if trajectory is not None else []
    if tool_calls is None and isinstance(trajectory, dict):
        tool_calls = trajectory.get("tool_calls", [])
    tool_calls = list(tool_calls or [])

    successful_calls = [call for call in tool_calls if _tool_call_success(call)]
    failed_calls = [call for call in tool_calls if not _tool_call_success(call)]
    successful_tool_names = [_tool_call_name(call) for call in successful_calls]
    failed_tool_names = [_tool_call_name(call) for call in failed_calls]
    attempted_tool_names = [_tool_call_name(call) for call in tool_calls]
    mutation_tool_names = [
        name for name in successful_tool_names if name in _MUTATION_TOOL_NAMES
    ]
    read_tool_names = [
        name for name in successful_tool_names if _is_read_like_tool(name)
    ]
    artifact_write_tools = [
        name for name in successful_tool_names if name in _ARTIFACT_WRITE_TOOL_NAMES
    ]

    read_after_mutation = False
    seen_mutation = False
    for call in successful_calls:
        name = _tool_call_name(call)
        if name in _MUTATION_TOOL_NAMES:
            seen_mutation = True
        elif seen_mutation and _is_read_like_tool(name):
            read_after_mutation = True
            break

    n_successful = getattr(trajectory, "num_successful_tool_calls", None)
    if n_successful is None and isinstance(trajectory, dict):
        n_successful = trajectory.get("num_successful_tool_calls")
    if n_successful is None:
        n_successful = len(successful_calls)

    effective_target_n = target_n
    if effective_target_n is None and sampling_result is not None:
        effective_target_n = getattr(sampling_result, "target_n", None)
    if effective_target_n is None and trajectory is not None:
        effective_target_n = getattr(trajectory, "target_n", None)
    if effective_target_n is None and isinstance(trajectory, dict):
        effective_target_n = trajectory.get("target_n")

    quality_stats = getattr(trajectory, "quality_stats", None)
    if quality_stats is None and isinstance(trajectory, dict):
        quality_stats = trajectory.get("quality_stats", {})
    quality_stats = quality_stats or {}

    state_changed = None
    state_hash_before = None
    state_hash_after = None
    if isinstance(state_evidence, dict):
        state_changed = state_evidence.get("changed")
        state_hash_before = state_evidence.get("s0_hash") or state_evidence.get(
            "state_hash_before"
        )
        state_hash_after = state_evidence.get("s1_hash") or state_evidence.get(
            "state_hash_after"
        )

    anchor_final = {}
    if isinstance(anchor_usage, dict):
        anchor_final = anchor_usage.get("final_prefix") or {}

    quality_notes: List[str] = []
    if effective_target_n is not None and n_successful < effective_target_n:
        quality_notes.append("target_n_not_met")
    if failed_calls:
        quality_notes.append("tool_failures_present")
    if state_changed is True and not mutation_tool_names:
        quality_notes.append("state_changed_without_known_mutation_tool")
    if mutation_tool_names and not read_after_mutation:
        quality_notes.append("mutation_without_readback")
    if (
        quality_stats.get("skills_total")
        and quality_stats.get("skill_guided_complete") is False
    ):
        quality_notes.append("skill_guided_incomplete")
    if anchor_final.get("missing_anchors"):
        quality_notes.append("anchor_missing")

    if state_changed is True and mutation_tool_names and read_after_mutation:
        quality_bucket = "mutation_with_readback"
    elif state_changed is True and mutation_tool_names:
        quality_bucket = "mutation_without_readback"
    elif state_changed is True:
        quality_bucket = "state_changed_without_known_mutation_tool"
    elif n_successful >= 5 and len(set(successful_tool_names)) >= 3:
        quality_bucket = "deep_retrieval"
    elif n_successful >= 1:
        quality_bucket = "shallow_retrieval_or_partial"
    else:
        quality_bucket = "empty_or_failed"

    signals = {
        "target": {
            "target_n": effective_target_n,
            "successful_tool_calls": n_successful,
            "target_satisfied": (
                bool(n_successful >= effective_target_n)
                if effective_target_n is not None
                else None
            ),
        },
        "tool_usage": {
            "total_tool_calls": len(tool_calls),
            "successful_tool_calls": len(successful_calls),
            "failed_tool_calls": len(failed_calls),
            "distinct_tools_attempted": len(set(attempted_tool_names)),
            "distinct_tools_successful": len(set(successful_tool_names)),
            "tools_attempted": _ordered_unique_strings(attempted_tool_names),
            "tools_successful": _ordered_unique_strings(successful_tool_names),
            "tools_failed": _ordered_unique_strings(failed_tool_names),
            "mutation_tool_calls": len(mutation_tool_names),
            "mutation_tools": _ordered_unique_strings(mutation_tool_names),
            "read_tool_calls": len(read_tool_names),
            "read_tools": _ordered_unique_strings(read_tool_names),
            "artifact_write_calls": len(artifact_write_tools),
            "artifact_write_tools": _ordered_unique_strings(artifact_write_tools),
            "read_after_mutation": read_after_mutation,
        },
        "state": {
            "changed": state_changed,
            "hash_before": state_hash_before,
            "hash_after": state_hash_after,
            "total_changes": state_evidence.get("total_changes")
            if isinstance(state_evidence, dict)
            else None,
            "summary": state_evidence.get("summary")
            if isinstance(state_evidence, dict)
            else None,
        },
        "anchors": {
            "status": anchor_final.get("status"),
            "coverage_ratio": anchor_final.get("anchor_coverage_ratio"),
            "used": anchor_final.get("used_anchors", []),
            "missing": anchor_final.get("missing_anchors", []),
            "required": (anchor_usage or {}).get("required_anchors", [])
            if isinstance(anchor_usage, dict)
            else [],
        },
        "skills": {
            "skills_total": quality_stats.get("skills_total"),
            "skills_completed": quality_stats.get("skills_completed"),
            "skill_guided_complete": quality_stats.get("skill_guided_complete"),
        },
        "collection": {
            "stage": sampling_result.stage if sampling_result else None,
            "tier": sampling_result.tier if sampling_result else None,
            "phase": sampling_result.phase if sampling_result else None,
            "checkpoint_failures": (checkpoint_stats or {}).get("failures"),
            "checkpoint_rollbacks": (checkpoint_stats or {}).get("rollbacks"),
        },
        "quality_bucket": quality_bucket,
        "quality_notes": quality_notes,
    }
    return {k: v for k, v in signals.items() if v is not None}


def _build_experience_context(
    *,
    task_config,
    selected_env,
    reset_meta: Dict[str, Any],
    episode_world_context: Dict[str, Any],
    sampling_result: Optional[SamplingResult],
    tool_names: List[str],
    task_type,
    retrieval_spec=None,
    intent_spec=None,
    state_evidence: Optional[Dict[str, Any]] = None,
    anchor_usage: Optional[Dict[str, Any]] = None,
    trajectory=None,
) -> Dict[str, Any]:
    """Build visible, non-leaky context for experience extraction/retrieval."""
    configured_context = episode_world_context or {}
    selected_domain = (
        reset_meta.get("selected_domain")
        or configured_context.get("domain")
        or getattr(selected_env, "name", None)
        or getattr(task_config, "task_type", "unknown")
    )
    task_type_value = getattr(task_type, "value", task_type) if task_type else None
    successful_tools = _safe_tool_names_from_trajectory(trajectory)

    context = {
        "engine": "EGTS",
        "world_id": reset_meta.get("output_namespace")
        or getattr(selected_env, "output_namespace", None)
        or getattr(selected_env, "name", None),
        "world_domain": selected_domain,
        "operator_role": configured_context.get("operator_role"),
        "task_type": task_type_value,
        "stage": sampling_result.stage if sampling_result else None,
        "tier": sampling_result.tier if sampling_result else None,
        "phase": sampling_result.phase if sampling_result else None,
        "target_n": getattr(sampling_result, "target_n", None)
        if sampling_result
        else None,
        "visible_tools": tool_names,
        "successful_tools": successful_tools,
        "base_tools": sampling_result.base_tools_used if sampling_result else [],
        "anchor_tools": sampling_result.anchor_tools_used if sampling_result else [],
        "required_anchors": sampling_result.anchors if sampling_result else [],
        "anchor_usage": anchor_usage or {},
        "state_evidence": state_evidence or {},
    }
    if retrieval_spec is not None and hasattr(retrieval_spec, "get_summary"):
        context["retrieval_summary"] = retrieval_spec.get_summary()
    if intent_spec is not None and hasattr(intent_spec, "to_dict"):
        intent_data = intent_spec.to_dict()
        context["intent_summary"] = {
            "primary_action": intent_data.get("primary_action"),
            "affected_paths": intent_data.get("affected_paths"),
            "changed_tools": intent_data.get("tools_used"),
        }

    return {k: v for k, v in context.items() if v not in (None, "", [], {})}


def _format_experience_context_for_prompt(context: Dict[str, Any]) -> str:
    """Compact context string for experience prompt injection."""
    lines = []
    for key in (
        "world_domain",
        "operator_role",
        "task_type",
        "stage",
        "tier",
        "phase",
        "target_n",
        "visible_tools",
        "successful_tools",
        "anchor_usage",
        "retrieval_summary",
        "intent_summary",
    ):
        value = context.get(key)
        if value not in (None, "", [], {}):
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) if lines else "No additional visible context."


def _build_data_source_metadata(selected_env=None, reset_meta=None, init_summary=None) -> dict:
    """Build stable source metadata without using it as the artifact namespace."""
    reset_meta = reset_meta if isinstance(reset_meta, dict) else {}
    init_summary = init_summary if isinstance(init_summary, dict) else {}
    selected_benchmark_env = init_summary.get("selected_benchmark_env")
    if not isinstance(selected_benchmark_env, dict):
        selected_benchmark_env = {}

    name = (
        reset_meta.get("output_namespace")
        or reset_meta.get("benchmark_env_id")
        or reset_meta.get("selected_domain")
        or selected_benchmark_env.get("name")
        or getattr(selected_env, "name", None)
    )
    namespace = (
        reset_meta.get("output_namespace")
        or selected_benchmark_env.get("output_namespace")
        or getattr(selected_env, "output_namespace", None)
        or name
    )

    metadata = {
        "name": name or "unknown",
        "namespace": namespace or "unknown",
        "selected_env": getattr(selected_env, "name", None),
        "selected_domain": reset_meta.get("selected_domain"),
        "benchmark_env_id": reset_meta.get("benchmark_env_id"),
        "source_output_namespace": reset_meta.get("output_namespace"),
    }
    return {k: v for k, v in metadata.items() if v is not None}


def _build_episode_initial_user_message(
    *,
    selected_env=None,
    reset_meta: Optional[Dict[str, Any]] = None,
    episode_world_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Build task-grounding user message from benchmark-world reset metadata.

    Benchmark task injection has been removed in favor of objective-driven
    exploration (see prompts/exploration.py:EXPLORATION_USER_PROMPT_WITH_OBJECTIVE).
    The model now conceives its own task objectives from world context and
    available tools, producing more diverse and natural trajectories.
    """
    return None


def _extract_stated_objective(trajectory) -> Optional[str]:
    """Extract the model's stated objective from its first assistant message.

    When using objective-driven exploration, the model is prompted to state
    "I will [concrete task objective]" before making any tool calls. This
    function extracts that statement so it can be saved as a problem candidate
    in raw_context and forwarded to the synthesis pipeline.
    """
    if trajectory is None:
        return None
    messages = getattr(trajectory, "messages", None) or []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = str(msg.get("content", "") or "").strip()
        if not content:
            continue
        # Only count as an objective statement if there are no tool calls
        # in this turn (pure text, not a function-calling assistant message).
        if msg.get("tool_calls"):
            continue
        # Match "I will ..." patterns.
        lowered = content.lower()
        if lowered.startswith("i will ") or "i will " in lowered[:200]:
            # Return the first sentence or the whole statement (up to 300 chars)
            for end_char in (". ", ".\n", "\n\n", "\n", ".", "!"):
                idx = content.find(end_char)
                if 10 <= idx <= 300:
                    return content[:idx + 1].strip()
            return content[:300].strip()
        # Also accept explicit task statements without "I will" prefix.
        if lowered.startswith("my objective") or lowered.startswith("my task"):
            return content[:300].strip()
    return None


def _world_state_hash_view(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return stable state-fingerprint fields from an executable-world state response."""
    if not isinstance(state, dict):
        return {}
    hash_view = {k: v for k, v in state.items() if k.endswith("_hash")}
    if hash_view:
        return hash_view
    ignored = {
        "status",
        "episode_id",
        "tool_call_count",
        "call_count",
        "request_count",
    }
    return {k: v for k, v in state.items() if k not in ignored}


_LOCAL_COPY_TOOL = "__local_copy_tree__"
_FS_BENCHMARK_REPO_CACHE: dict[str, FilesystemBenchmarkRepository] = {}


class _WorldStateDiff:
    """Lightweight diff object for benchmark worlds that use hash-based state comparison.

    Compatible with the diff interface expected by determine_task_type():
    - is_empty() returns True if state did not change
    - get_change_summary() returns a human-readable summary
    """

    def __init__(self, changed: bool, s0: dict, s1: dict):
        self.changed = changed
        self.s0 = s0
        self.s1 = s1

    def is_empty(self) -> bool:
        return not self.changed

    def total_changes(self) -> int:
        return 1 if self.changed else 0

    def get_change_summary(self) -> str:
        if self.changed:
            return f"World state changed (S0={self.s0}, S1={self.s1})"
        return "World state unchanged"


def setup_logging(config):
    """Set up logging configuration."""
    log_level = getattr(logging, config.logging.level.upper())

    handlers = [logging.StreamHandler()]

    # Place log file in output directory for the experiment
    if config.logging.file:
        output_dir = Path(config.pipeline.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        exp_name = config.pipeline.exp_name
        if not exp_name or exp_name.strip() == "":
            exp_name = f"exp_default"
        exp_dir = output_dir / exp_name
        exp_dir.mkdir(parents=True, exist_ok=True)

        log_file = exp_dir / config.logging.file
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=log_level, format=config.logging.format, handlers=handlers
    )

    logger = logging.getLogger(__name__)
    if config.logging.file:
        logger.info(f"Logging to file: {exp_dir / config.logging.file}")


def _get_filesystem_benchmark_repo(task_config, root_str: str):
    """Get or create benchmark repository for filesystem init."""
    workspace_root = Path(root_str).resolve().parent
    benchmark_roots = list(getattr(task_config, "benchmark_roots", ["../eval"]))
    benchmark_source = getattr(task_config, "benchmark_source", "all")
    cache_subdir = getattr(
        task_config, "benchmark_cache_subdir", "benchmark_envs/filesystem"
    )
    include_local_dirs = bool(getattr(task_config, "benchmark_include_local_dirs", True))
    download_timeout_sec = int(
        getattr(task_config, "benchmark_download_timeout_sec", 900)
    )
    max_environments = getattr(task_config, "benchmark_max_environments", None)

    cache_key = "|".join(
        [
            str(workspace_root),
            cache_subdir,
            benchmark_source,
            ",".join(str(Path(p).resolve()) for p in benchmark_roots),
            str(include_local_dirs),
            str(download_timeout_sec),
            str(max_environments),
        ]
    )

    repo = _FS_BENCHMARK_REPO_CACHE.get(cache_key)
    if repo is None:
        repo = FilesystemBenchmarkRepository(
            benchmark_roots=benchmark_roots,
            workspace_root=str(workspace_root),
            cache_subdir=cache_subdir,
            benchmark_source=benchmark_source,
            include_local_dirs=include_local_dirs,
            download_timeout_sec=download_timeout_sec,
            max_environments=max_environments,
        )

        if getattr(task_config, "benchmark_deploy_all", True):
            repo.deploy_all_environments()

        _FS_BENCHMARK_REPO_CACHE[cache_key] = repo

    return repo


def _build_init_plan(task_config, init_generator, root_str: str):
    """Build task-specific initialization plan."""
    task_type = getattr(task_config, "task_type", "filesystem")

    if task_type == "filesystem":
        from .config.tasks.filesystem import FilesystemTaskConfig
        if not isinstance(task_config, FilesystemTaskConfig):
            # Generic task config — use default init
            size_profile = getattr(task_config, "size_profile", "small")
            return init_generator.generate_init_plan(root_str, size_profile)
        size_profile = getattr(task_config, "size_profile", "small")
        init_mode = getattr(task_config, "init_mode", "random")
        benchmark_ratio = float(getattr(task_config, "benchmark_ratio", 0.5))
        benchmark_ratio = max(0.0, min(1.0, benchmark_ratio))
        seed = int(getattr(init_generator, "seed", random.randint(0, 2**32 - 1)))

        use_benchmark = False
        if init_mode == "benchmark":
            use_benchmark = True
        elif init_mode == "hybrid":
            use_benchmark = random.Random(seed).random() < benchmark_ratio
        elif init_mode != "random":
            logging.getLogger(__name__).warning(
                f"Unknown filesystem init_mode '{init_mode}', fallback to random"
            )

        if use_benchmark:
            repo = _get_filesystem_benchmark_repo(task_config, root_str)
            env = repo.pick_environment(seed=seed)
            if env is not None:
                init_plan = repo.create_init_plan(root=root_str, seed=seed, env=env)
                init_summary = init_plan.get_summary()
                init_summary["selected_benchmark_env"] = {
                    "name": env.env_id,
                    "prompt_domain": getattr(task_config, "prompt_domain", None) or "filesystem",
                    "output_namespace": getattr(task_config, "output_namespace", None) or env.env_id,
                    "tool_metadata": getattr(task_config, "tool_metadata", {}) or {},
                }
                return init_plan

            logging.getLogger(__name__).warning(
                "No deployed benchmark environments available; fallback to random init"
            )

        return init_generator.generate_init_plan(root_str, size_profile)

    if task_type == "playwright":
        starting_url = getattr(task_config, "starting_url", None)
        init_complexity = getattr(task_config, "init_complexity", "simple")
        return init_generator.generate_init_plan(starting_url, init_complexity)

    if task_type == "postgres":
        # Postgres init generator keeps a generic first parameter for compatibility.
        database = getattr(task_config, "database", "mcpgen")
        schema_complexity = getattr(task_config, "schema_complexity", "simple")
        return init_generator.generate_init_plan(database, schema_complexity)

    # Fallback for unknown task configs: keep legacy behavior
    size_profile = getattr(task_config, "size_profile", "small")
    return init_generator.generate_init_plan(root_str, size_profile)


def _init_plan_to_operations(init_plan) -> list[dict]:
    """Convert init plan to operations list in a task-agnostic way."""
    if init_plan is None:
        return []
    if isinstance(init_plan, dict) and "operations" in init_plan:
        return init_plan["operations"] or []
    if hasattr(init_plan, "to_operations") and callable(init_plan.to_operations):
        return init_plan.to_operations()
    return []


def _copy_tree_into_workspace(arguments: dict) -> dict:
    """Execute local tree copy operation for environment initialization."""
    source = Path(arguments.get("source", "")).resolve()
    target = Path(arguments.get("target", "")).resolve()
    exclude = set(arguments.get("exclude", []))
    clean_target = bool(arguments.get("clean_target", False))

    if not source.exists():
        raise FileNotFoundError(f"Init source not found: {source}")

    target.mkdir(parents=True, exist_ok=True)
    if clean_target:
        for item in target.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    copied_entries = 0
    for item in source.iterdir():
        if item.name in exclude:
            continue
        dest = target / item.name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()

        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
        copied_entries += 1

    return {
        "source": str(source),
        "target": str(target),
        "copied_entries": copied_entries,
    }


def _to_serializable(value):
    """Best-effort conversion to JSON-serializable data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {str(k): _to_serializable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(v) for v in value]

    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _to_serializable(value.to_dict())
        except Exception:
            pass

    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return _to_serializable(value.model_dump())
        except Exception:
            pass

    if hasattr(value, "value"):
        try:
            return _to_serializable(value.value)
        except Exception:
            pass

    return str(value)


def _record_iteration_failures(
    storage: Storage,
    trajectory,
    checkpoint_stats: Optional[dict],
    episode_id: str,
):
    """Record failure statistics from either recoverable stats or trajectory calls."""
    if checkpoint_stats:
        failure_events = checkpoint_stats.get("failure_events", []) or []
        for event in failure_events:
            if not isinstance(event, dict):
                continue
            storage.record_tool_failure(
                tool_name=str(event.get("tool_name", "unknown")),
                reason=str(event.get("error_type", "unknown")),
                episode_id=episode_id,
                error_message=str(event.get("error_message", "")),
            )

        total_failures = int(
            checkpoint_stats.get("total_failures", len(failure_events)) or 0
        )
        storage.record_episode_failures(num_failures=total_failures, episode_id=episode_id)
        return

    if trajectory is None:
        return

    # Strict mode fallback: derive failure stats from unsuccessful tool calls.
    failed_calls = [tc for tc in getattr(trajectory, "tool_calls", []) if not tc.success]
    for tc in failed_calls:
        error_message = tc.error_message or ""
        reason = "execution_error"
        if "invalid json" in error_message.lower():
            reason = "invalid_args"
        storage.record_tool_failure(
            tool_name=tc.tool_name,
            reason=reason,
            episode_id=episode_id,
            error_message=error_message,
        )
    if failed_calls:
        storage.record_episode_failures(
            num_failures=len(failed_calls), episode_id=episode_id
        )


async def _execute_init_plan(init_plan, mcp_client) -> list[dict]:
    """Execute init plan operations with MCP client."""
    logger = logging.getLogger(__name__)
    operations = _init_plan_to_operations(init_plan)
    results = []

    for op in operations:
        tool = op.get("tool")
        arguments = op.get("arguments", {})
        try:
            if tool == _LOCAL_COPY_TOOL:
                result = _copy_tree_into_workspace(arguments)
            else:
                result = await mcp_client.call_tool(tool, arguments)
            results.append(
                {"success": True, "operation": op, "result": result}
            )
        except Exception as e:
            logger.error(f"Failed to execute init operation {op}: {e}")
            results.append({"success": False, "operation": op, "error": str(e)})

    logger.info(
        f"Init plan executed: {sum(1 for r in results if r['success'])}/{len(results)} operations succeeded"
    )
    return results


def _create_snapshot_provider(snapshot_provider_class, mcp_client, root_str: str):
    """Create snapshot provider with compatibility for different constructor styles."""
    logger = logging.getLogger(__name__)

    # Preferred: explicit kwargs (filesystem provider expects these).
    try:
        return snapshot_provider_class(mcp_client=mcp_client, root=root_str)
    except TypeError:
        pass

    # Fallback: positional args.
    try:
        return snapshot_provider_class(mcp_client, root_str)
    except TypeError:
        pass

    # Final fallback: no-arg providers (playwright/postgres style).
    try:
        return snapshot_provider_class()
    except TypeError as e:
        sig = "unknown"
        try:
            sig = str(inspect.signature(snapshot_provider_class))
        except Exception:
            pass
        logger.error(
            "Failed to instantiate snapshot provider %s with signature %s: %s",
            snapshot_provider_class,
            sig,
            e,
        )
        raise


from data_collection.config.tasks.filesystem import FilesystemTaskConfig

from data_collection.init_factory import EnvInitGeneratorFactory
from data_collection.intent_builder import build_intent_spec


async def _cleanup_world_session(client, server_name: str, logger) -> None:
    """Close the episode runtime via /admin/close before disconnecting the MCP transport.

    This prevents session leaks in the EpisodeRegistry. Without this call,
    every active episode stays permanently bound in the registry until the
    container is restarted.
    """
    if hasattr(client, "admin_request"):
        try:
            await client.admin_request("/admin/close", method="POST")
            logger.debug(f"Closed world session for {server_name}")
        except Exception:
            # /admin/close may 404 on worlds without EpisodeRegistry, or
            # fail if the server is already unreachable — both are non-fatal.
            pass


async def run_single_iteration_trajs2data(
    mcp_server_name: str,
    config,
    maas_client: MaaSClient,
    storage: Storage,
    iteration: int,
    server_manager: MCPServerManager,
    sampler: Optional[StageAwareSampler] = None,
    coverage_tracker: Optional[CoverageTracker] = None,
    efficiency_monitor: Optional[EfficiencyMonitor] = None,
    exploration_recorder: Optional[ExplorationStateRecorder] = None,
    embedding_provider: Optional[OpenAICompatibleEmbedding] = None,
    experience_manager: Optional[ExperienceManager] = None,
    pre_started_clients: Optional[dict] = None,
    reuse_workspace: Optional[Path] = None,
    coverage_tracker_cache: Optional[dict] = None,
    selected_env=None,
) -> bool:
    """Run a single iteration using trajs2data mode with retry support.

    This implements the Traj→Problem pipeline:
    1. Initialize environment (S0)
    2. Sample tools using phase-aware sampler
    3. Run strict trajectory collection (with retry on failure)
    4. Snapshot environment (S1) and compute diff
    5. Synthesize problem (dual-mode: mutation or retrieval)
    6. Save problem + trajectory with rich metadata

    Args:
        mcp_server_name: Name of MCP server to use
        config: Configuration object
        maas_client: MaaS client
        storage: Storage manager
        iteration: Current iteration number
        sampler: Optional phase-aware sampler (created if not provided)
        coverage_tracker: Optional coverage tracker (created if not provided)

    Returns:
        True if a valid trajectory was collected and saved, False otherwise
    """
    logger = logging.getLogger(__name__)
    logger.info(f"\n{'=' * 60}")
    logger.info(
        f"[TRAJS2DATA MODE] Iteration {iteration} - MCP Server: {mcp_server_name}"
    )
    logger.info(f"{'=' * 60}\n")

    trajs2data_cfg = config.trajs2data
    save_filtered_enabled = bool(
        getattr(trajs2data_cfg, "save_filtered", False)
        or getattr(getattr(config, "pipeline", None), "save_failed", False)
    )

    def _save_filtered_if_enabled(
        reason: str,
        *,
        filter_stage: str,
        trajectory_obj=None,
        attempt: Optional[int] = None,
    ) -> None:
        if not save_filtered_enabled:
            return
        try:
            if trajectory_obj is not None and hasattr(trajectory_obj, "to_dict"):
                trajectory_payload = trajectory_obj.to_dict()
            elif isinstance(trajectory_obj, dict):
                trajectory_payload = trajectory_obj
            else:
                trajectory_payload = {
                    "status": "error",
                    "abort_reason": reason,
                    "num_steps": 0,
                    "tool_calls": [],
                    "messages": [],
                }

            storage.save_trajs2data_filtered(
                trajectory_payload,
                mcp_server_name,
                iteration,
                reason,
                attempt=attempt,
                filter_stage=filter_stage,
                metadata_extra={
                    "output_namespace": output_namespace,
                    "artifact_namespace": getattr(task_config, "artifact_namespace", ""),
                    "data_source": _build_data_source_metadata(
                        selected_env=selected_env,
                        reset_meta=locals().get("_episode_reset_meta", {}),
                        init_summary=locals().get("init_summary", {}),
                    ),
                },
            )
        except Exception as save_err:
            logger.warning(
                f"Failed to save filtered sample (stage={filter_stage}, iteration={iteration}): {save_err}"
            )

    # Polymorphic task config access
    task_config = trajs2data_cfg.task

    # Determine primary server from task config
    primary_server = task_config.primary_server or task_config.required_servers[0]

    # Verify the requested server matches task requirements
    if mcp_server_name not in task_config.required_servers:
        logger.warning(
            f"Server '{mcp_server_name}' not in task's required_servers: {task_config.required_servers}"
        )
        # For backward compatibility, allow if primary_server matches
        if mcp_server_name != primary_server:
            logger.error(f"Server mismatch: requested '{mcp_server_name}', task requires '{primary_server}'")
            _save_filtered_if_enabled(
                reason=(
                    f"Server mismatch: requested '{mcp_server_name}', "
                    f"task requires '{primary_server}'"
                ),
                filter_stage="precheck_server_mismatch",
            )
            return False

    tool_curriculum_cfg = getattr(trajs2data_cfg, "tool_curriculum", None)
    language = getattr(trajs2data_cfg, "language", "en")

    # Compute seed for this iteration
    seed_base = getattr(task_config, "seed_base", None)
    if seed_base is not None:
        episode_seed = seed_base + iteration
    else:
        episode_seed = random.randint(0, 2**32 - 1)

    # Get max_attempts from config or default to 3
    max_attempts = getattr(trajs2data_cfg, "max_attempts", 3)
    synthesis_in_collection = getattr(trajs2data_cfg, "synthesis_in_collection", True)

    # Get tool configuration from TaskConfig
    read_only_tools = task_config.read_only_tools
    read_only_tools_priority = task_config.read_only_tools_priority
    prompt_domain = getattr(task_config, "prompt_domain", None) or primary_server
    output_namespace = getattr(task_config, "output_namespace", None) or primary_server
    episode_world_context = _build_episode_world_context(task_config, selected_env)
    resolved_tool_metadata = None
    debug_log_path = getattr(config.logging, "debug_log_path", None)

    workspace_path = None
    attempt_success = False
    cleanup_success = False
    last_filter_reason = None
    sampling_result: Optional[SamplingResult] = None
    init_summary: dict = {}
    owns_servers = pre_started_clients is None  # Only manage lifecycle if we started them

    try:
        # Create or reuse workspace
        if reuse_workspace is not None:
            workspace_path = reuse_workspace
            # Clean workspace contents for reuse (keep directory itself)
            for child in workspace_path.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        else:
            workspace_path = (
                Path(config.local.workspace_root) / f"trajs2data_{iteration:06d}"
            )
            workspace_path.mkdir(parents=True, exist_ok=True)
        root_str = str(workspace_path.resolve())

        logger.info(f"📁 Workspace: {workspace_path}")
        logger.info(f"🎲 Seed: {episode_seed}")
        logger.info(f"🔄 Max attempts: {max_attempts}")

        # Get adapters for primary server (may be empty for benchmark worlds)
        adapters = server_manager.get_adapters(primary_server)
        has_adapters = bool(adapters)
        if has_adapters:
            logger.info(f"📦 Using adapters from server: {primary_server}")
        else:
            logger.info(
                f"📦 Server '{primary_server}' has no adapters "
                f"(benchmark world manages its own init/snapshot/diff)"
            )

        # Start or reuse MCP servers
        if pre_started_clients is not None:
            mcp_clients = pre_started_clients
        else:
            mcp_clients = {}
            for server_name in task_config.required_servers:
                logger.info(f"🚀 Starting server: {server_name}")
                if server_name in getattr(config, "http_mcp_servers", {}):
                    server_cfg = config.http_mcp_servers[server_name]
                    run_id = getattr(config.pipeline, "exp_name", None) or "exp_default"
                    mcp_clients[server_name] = await server_manager.start_server(
                        server_name,
                        iteration,
                        workspace_path=root_str,
                        url=server_cfg.url,
                        headers=build_world_session_headers(
                            getattr(server_cfg, "headers", {}) or {},
                            run_id=run_id,
                            worker_id=0,
                        ),
                    )
                else:
                    mcp_clients[server_name] = await server_manager.start_server(
                        server_name, iteration, workspace_path=root_str
                    )

        # Get primary client for main operations
        mcp_client = mcp_clients[primary_server]

        # Run prepare hook if defined
        if task_config.prepare_hook:
            logger.info(f"🔧 Running prepare hook: {task_config.prepare_hook}")
            # TODO: Implement lifecycle hook execution
            # await _run_lifecycle_hook(task_config.prepare_hook, workspace_path, mcp_clients)

        # ============================================================
        # STEP 1: Initialize Environment (S0)
        # ============================================================
        init_plan = None
        snapshot_s0 = None
        snapshot_provider = None
        _episode_reset_meta = {}  # dynamic metadata from benchmark world /admin/reset
        reset_strategy = "none"
        state_strategy = "none"

        if has_adapters and "init_generator" in adapters:
            logger.info(f"🔧 Step 1: Initializing environment (S0)")
            reset_strategy = "adapter_init_plan"

            # Get init generator from adapters
            init_generator_class = adapters["init_generator"]
            init_generator = init_generator_class(seed=episode_seed)

            # Generate init plan (deterministic based on seed)
            init_plan = _build_init_plan(task_config, init_generator, root_str)
            init_summary = (
                init_plan.get_summary()
                if hasattr(init_plan, "get_summary") and callable(init_plan.get_summary)
                else {}
            )

            logger.info(f"  Generated init plan: {init_summary}")

            # Execute init operations
            init_results = await _execute_init_plan(init_plan, mcp_client)
            init_success = sum(1 for r in init_results if r["success"])

            if init_results and init_success < len(init_results) * 0.8:
                logger.warning(
                    f"  Init plan partially failed: {init_success}/{len(init_results)}"
                )

            logger.info(
                f"  ✓ Environment initialized: {init_success}/{len(init_results)} operations"
            )

            # Take S0 snapshot using adapter
            if "snapshot_provider" in adapters:
                logger.info(f"📸 Taking S0 snapshot...")
                state_strategy = "adapter_snapshot_diff"
                snapshot_provider_class = adapters["snapshot_provider"]
                snapshot_provider = _create_snapshot_provider(
                    snapshot_provider_class, mcp_client, root_str
                )
                snapshot_s0 = await snapshot_provider.create_snapshot(root_str)

                snapshot_size = len(snapshot_s0.files) if hasattr(snapshot_s0, 'files') else 'N/A'
                logger.info(f"  S0 snapshot created (size: {snapshot_size})")
        else:
            # Benchmark world: environment is managed externally (e.g. via the world /admin/reset endpoint)
            logger.info(
                f"🔧 Step 1: Skipping local init (benchmark world manages environment via admin endpoints)"
            )
            reset_strategy = "admin_reset"
            init_summary = {}
            _episode_reset_meta = {}  # dynamic metadata from /admin/reset

            if hasattr(mcp_client, "admin_request"):
                # --- Call /admin/reset to initialize a new episode ---
                try:
                    reset_body = {}
                    # Pass domain selection config if available
                    _enabled_task_types = getattr(task_config, "enabled_task_types", None)
                    _task_type_selection = getattr(task_config, "task_type_selection", None)
                    _task_type_weights = getattr(task_config, "task_type_weights", None)
                    if _enabled_task_types:
                        reset_body["enabled_domains"] = _enabled_task_types
                    if _task_type_selection:
                        reset_body["domain_selection_mode"] = _task_type_selection
                    if _task_type_weights:
                        reset_body["domain_weights"] = _task_type_weights
                    reset_body["seed"] = iteration

                    _episode_reset_meta = await mcp_client.admin_request(
                        "/admin/reset", method="POST", body=reset_body
                    )
                    logger.info(
                        f"  🌍 Episode reset: domain={_episode_reset_meta.get('selected_domain', '?')}, "
                        f"task={_episode_reset_meta.get('task_id', '?')}, "
                        f"tools={_episode_reset_meta.get('tool_count', '?')}"
                    )
                except Exception as e:
                    reason = (
                        f"Admin reset failed for {primary_server}: "
                        f"{type(e).__name__}: {e}"
                    )
                    logger.warning(f"  {reason}")
                    _save_filtered_if_enabled(
                        reason=reason,
                        filter_stage="admin_reset_failed",
                    )
                    return False

                # --- Capture S0 state hash ---
                try:
                    state_s0_response = await mcp_client.admin_request("/admin/state")
                    snapshot_s0 = state_s0_response  # dict with agent_db_hash, user_db_hash
                    state_strategy = "admin_state_hash"
                    logger.info(f"  📸 S0 state hash captured from benchmark world: {snapshot_s0}")
                except Exception as e:
                    logger.warning(f"  Could not capture S0 state hash: {e}")

        # ============================================================
        # STEP 2: Sample Tools using Phase-Aware Sampler
        # ============================================================
        logger.info(f"🔧 Step 2: Sampling tools (phase-aware)")

        # Collect tools from ALL servers
        all_tools = []
        for server_name, client in mcp_clients.items():
            server_tools = await client.list_tools()
            # Tag tools with server name for routing
            for tool in server_tools:
                tool["_server"] = server_name
            all_tools.extend(server_tools)
            logger.info(f"  Found {len(server_tools)} tools from {server_name}")
        if not all_tools:
            logger.warning(f"No tools available from {mcp_server_name}")
            _save_filtered_if_enabled(
                reason=f"No tools available from {mcp_server_name}",
                filter_stage="no_tools_available",
            )
            return False

        # Create sampler if not provided
        server_metadata = _get_server_metadata(
            config,
            mcp_server_name,
            selected_env=selected_env
            or (init_summary.get("selected_benchmark_env") if isinstance(init_summary, dict) else None),
        )

        # Override server_metadata with per-episode dynamic metadata from /admin/reset
        if _episode_reset_meta:
            server_metadata["_prefer_server_metadata"] = True
            for key in (
                "prompt_domain",
                "output_namespace",
                "tool_metadata",
                "read_only_tools",
                "read_only_tools_priority",
            ):
                if key in _episode_reset_meta:
                    server_metadata[key] = _episode_reset_meta[key]

        resolved_tool_metadata = ToolMetadataResolver(
            task_config=task_config,
            server_name=mcp_server_name,
            server_metadata=server_metadata,
        ).resolve(all_tools)

        # If /admin/reset returned tool_names for the current domain,
        # filter all_tools to only include tools from the active domain.
        _episode_tool_names = _episode_reset_meta.get("tool_names") if _episode_reset_meta else None
        if _episode_tool_names:
            _episode_tool_set = set(_episode_tool_names)
            all_tools_filtered = [
                t for t in all_tools
                if (t.get("name") or t.get("function", {}).get("name", "")) in _episode_tool_set
            ]
            if all_tools_filtered:
                logger.info(
                    f"  🔍 Filtered tools to current domain: {len(all_tools_filtered)}/{len(all_tools)}"
                )
                all_tools = all_tools_filtered
                # Re-resolve metadata with filtered tools
                resolved_tool_metadata = ToolMetadataResolver(
                    task_config=task_config,
                    server_name=mcp_server_name,
                    server_metadata=server_metadata,
                ).resolve(all_tools)
        read_only_tools = resolved_tool_metadata["read_only_tools"]
        read_only_tools_priority = resolved_tool_metadata["read_only_tools_priority"]
        prompt_domain = resolved_tool_metadata["prompt_domain"]
        output_namespace = resolved_tool_metadata["output_namespace"]

        # Keep coverage beside the flattened collection artifacts by default.
        artifact_namespace = getattr(task_config, "artifact_namespace", "")

        # For explicit non-flat artifact namespaces, switch coverage tracker to match.
        if coverage_tracker_cache is not None and output_namespace and tool_curriculum_cfg is not None:
            coverage_key = artifact_namespace if artifact_namespace else "__root__"
            if coverage_key not in coverage_tracker_cache:
                coverage_tracker_cache[coverage_key] = CoverageTracker(
                    output_dir=storage.exp_dir / artifact_namespace,
                    track_file=tool_curriculum_cfg.coverage.track_file,
                    min_success_per_tool=tool_curriculum_cfg.coverage.min_success_per_tool,
                )
                logger.info(f"  📊 Created coverage tracker for artifact namespace: {artifact_namespace or '<root>'}")
            coverage_tracker = coverage_tracker_cache[coverage_key]

        if tool_curriculum_cfg is not None:
            resolved_base_tools = resolved_tool_metadata["base_tools"]
            if resolved_base_tools:
                tool_curriculum_cfg.base_tools = list(resolved_base_tools)
            else:
                logger.warning(
                    "No resolved base tools for %s; keeping configured base_tools=%s",
                    mcp_server_name,
                    list(getattr(tool_curriculum_cfg, "base_tools", []) or []),
                )

            resolved_anchor_tools = resolved_tool_metadata["anchor_tools"]
            if resolved_anchor_tools:
                tool_curriculum_cfg.anchor_tools = resolved_anchor_tools

        if sampler is None and tool_curriculum_cfg is not None:
            # Resolve domain for skill-guided exploration (skills_dir {domain} placeholder)
            _episode_domain = _episode_reset_meta.get("selected_domain") if _episode_reset_meta else None
            sampler = StageAwareSampler(
                config=tool_curriculum_cfg,
                all_tools=all_tools,
                coverage_tracker=coverage_tracker,
                project_root=Path.cwd(),
                domain=_episode_domain,
                read_only_tools=read_only_tools,
            )

        # Extract env_category from init_summary for skill filtering
        env_category = None
        if init_summary and "benchmark_env_id" in init_summary:
            env_id = init_summary["benchmark_env_id"]
            # Extract category from env_id format: {category}_{hash}
            env_category = env_id.rsplit("_", 1)[0] if "_" in env_id else None
            if env_category:
                logger.info(f"  Extracted env_category: '{env_category}' from env_id: '{env_id}'")
        if env_category is None and _episode_reset_meta:
            env_category = _episode_reset_meta.get("selected_domain") or _episode_reset_meta.get("category_id")
            if env_category:
                logger.info(f"  Using reset domain as env_category: '{env_category}'")

        # Sample using phase-aware sampler or fallback to random
        if sampler is not None:
            sampling_result = sampler.sample(
                env_category=env_category,
                current_iteration=iteration,
                total_iterations=getattr(config.pipeline, "num_iterations", None),
            )
            sampled_tools = sampling_result.exposed_tools
            effective_target_n = sampling_result.target_n

            logger.info(f"  Phase: {sampling_result.phase}")
            logger.info(f"  Target n: {effective_target_n}")
            logger.info(f"  Anchors: {sampling_result.anchors}")
        else:
            # Fallback to random sampling (legacy behavior)
            curriculum_cfg = getattr(trajs2data_cfg, "tool_curriculum", None) or getattr(trajs2data_cfg, "curriculum", None)
            n_tools_min = getattr(task_config, "n_tools_min", 2)
            n_tools_max = getattr(task_config, "n_tools_max", 6)
            n_tools = random.randint(n_tools_min, n_tools_max)
            n_tools = min(n_tools, len(all_tools))
            sampled_tools = random.sample(all_tools, n_tools)

            if curriculum_cfg:
                effective_target_n = random.randint(
                    curriculum_cfg.n_min, curriculum_cfg.n_max
                )
            else:
                effective_target_n = task_config.max_steps

            sampling_result = None

        tool_names = [
            t.get("name", t.get("function", {}).get("name", "unknown"))
            for t in sampled_tools
        ]
        logger.info(f"  Sampled {len(sampled_tools)} tools: {tool_names}")

        # Apply efficiency monitor adjustment if enabled
        original_target_n = effective_target_n
        if efficiency_monitor is not None:
            effective_target_n = efficiency_monitor.get_adjusted_target_n(
                effective_target_n
            )
            if effective_target_n != original_target_n:
                logger.info(
                    f"  ⚠️ Efficiency adjustment: target_n {original_target_n} → {effective_target_n}"
                )

        logger.info(f"  🎯 Target n (successful tool calls): {effective_target_n}")

        # ============================================================
        # STEP 3: Trajectory Collection (with retry loop)
        # ============================================================
        collector = Trajs2DataCollector(
            maas_client=maas_client,
            maas_config=config.maas,
            strict_mode=False,
            exploration_recorder=None,
            read_only_tools=read_only_tools,
        )

        # Prepare Directed Exploration Hint (PRD 4.1.2)
        # If we are in Phase1/2 (curriculum with anchors), explicitly tell the model
        # which tools it MUST use to avoid wasting the episode.
        tool_curriculum = getattr(trajs2data_cfg, "tool_curriculum", None)
        task_hint = ""
        use_exploration_objective = getattr(trajs2data_cfg, "use_exploration_objective", False)

        if tool_curriculum and sampling_result:
            # Identify "target tools" (Sampled - Base)
            base_tool_names = set(tool_curriculum.base_tools)
            sampled_tool_names = {
                t.get("name") or t.get("function", {}).get("name")
                for t in sampled_tools
            }

            # Target tools are those that are NOT base tools
            target_tools = list(sampled_tool_names - base_tool_names)

            if target_tools:
                if use_exploration_objective:
                    task_hint = (
                        f"\nNote: The following advanced tools are available and may be useful "
                        f"for your task: {', '.join(target_tools)}.\n"
                        f"If your objective naturally involves their capabilities, consider using them."
                    )
                else:
                    task_hint = (
                        f"\nIMPORTANT MISSION REQUIREMENT:\n"
                        f"You MUST use the following advanced tools to complete your task: {', '.join(target_tools)}.\n"
                        f"Design a task that specifically requires these capabilities."
                    )
                logger.info(
                    f"  💡 Directed Exploration Hint: {'Suggested' if use_exploration_objective else 'Must use'} {target_tools}"
                )

        # Retrieve relevant experience hints (PRD 4.7)
        if experience_manager is not None:
            tool_names_list = [
                t.get("name", t.get("function", {}).get("name", "unknown"))
                for t in sampled_tools
            ]

            # Get underused tools for boosting retrieval relevance
            preferred_tools = None
            if coverage_tracker:
                preferred_tools = coverage_tracker.get_low_coverage_tools(
                    tool_names_list
                )

            pre_collection_experience_context = _build_experience_context(
                task_config=task_config,
                selected_env=selected_env,
                reset_meta=_episode_reset_meta,
                episode_world_context=episode_world_context,
                sampling_result=sampling_result,
                tool_names=tool_names_list,
                task_type=None,
            )
            experience_hints = experience_manager.get_experience_hints(
                context=_format_experience_context_for_prompt(
                    pre_collection_experience_context
                ),
                tools=tool_names_list,
                preferred_tools=preferred_tools,
                source_namespace=output_namespace,
            )
            if experience_hints:
                logger.info(f"  💡 Injected experience hints")
                task_hint += experience_hints

        # Global Usage Feedback (PRD 4.1.2) - Inject coverage hints
        if coverage_tracker:
            tool_names_list = [
                t.get("name", t.get("function", {}).get("name", "unknown"))
                for t in sampled_tools
            ]

            # Get underused tools (low coverage)
            underused = coverage_tracker.get_low_coverage_tools(tool_names_list)
            # Get overused tools (high coverage)
            overused = coverage_tracker.get_high_coverage_tools(
                tool_names_list, top_k=3
            )

            if underused or overused:
                if use_exploration_objective:
                    usage_feedback = "\n\n[Usage Suggestions]\n"
                    if overused:
                        usage_feedback += f"- Tools like {', '.join(overused)} are commonly used. If they fit your objective, great — but also consider whether other tools could work.\n"
                    if underused:
                        suggested = underused[:3]
                        usage_feedback += f"- Tools like {', '.join(suggested)} haven't been explored much yet. If your task naturally involves them, feel free to try them.\n"
                else:
                    usage_feedback = "\n\n[Global Experience Feedback]\n"
                    if overused:
                        usage_feedback += f"- You have mastered: {', '.join(overused)}. Try to avoid overusing them if alternatives exist.\n"
                    if underused:
                        suggested = underused[:3]
                        usage_feedback += f"- Community knowledge gap: {', '.join(suggested)}. Prioritize using these if applicable.\n"

                task_hint += usage_feedback
                logger.info(f"  💡 Injected global usage feedback")

        # Load skill workflows if stage2_skill_guided
        # Sequential exposure: load only first skill for system prompt
        skill_workflow = None
        skill_selections_list = None
        if (
            sampling_result
            and sampling_result.stage == "stage2_skill_guided"
            and getattr(sampling_result, "skill_selections", None)
            and sampler is not None
            and getattr(sampler, "skill_sampler", None)
        ):
            try:
                skill_selections_list = sampling_result.skill_selections
                first_skill_id = skill_selections_list[0].skill_id

                # Load only first skill for system prompt (sequential exposure)
                skill_workflow = sampler.skill_sampler.load_single_skill_workflow(
                    first_skill_id, is_first=True
                )
                logger.info(
                    f"  📋 Loaded first skill for system prompt: {first_skill_id}"
                )
                if len(skill_selections_list) > 1:
                    logger.info(
                        f"  📋 Remaining skills for sequential injection: "
                        f"{[s.skill_id for s in skill_selections_list[1:]]}"
                    )
            except Exception as e:
                logger.warning(f"Failed to load skill workflow: {e}")
                skill_selections_list = None

        if trajs2data_cfg.exploration_system_prompt and (task_hint or skill_workflow):
            logger.warning(
                "Custom exploration_system_prompt is set — task_hint and skill_workflow "
                "will NOT be injected. Set exploration_system_prompt to null to enable "
                "dynamic prompt construction."
            )

        system_prompt = (
            trajs2data_cfg.exploration_system_prompt
            or build_exploration_system_prompt(
                root_dir=root_str,
                target_n=effective_target_n,
                task_hint=task_hint,
                task_config=task_config,
                skill_workflow=skill_workflow,
                world_context_override=episode_world_context,
                use_task_objective=getattr(trajs2data_cfg, "use_exploration_objective", False),
            )
        )
        initial_user_message = None
        trajectory = None
        diff = None
        task_type = None
        retrieval_spec = None
        checkpoint_stats = None

        # Determine collection mode
        # PRD: Phase 0 MUST use recoverable mode; later phases can be strict
        recoverable_cfg = getattr(trajs2data_cfg, "recoverable", None)
        config_enabled = recoverable_cfg and recoverable_cfg.enabled

        # Auto-enable recoverable for simple tier if available
        is_simple_tier = False
        if sampling_result:
            tier = getattr(sampling_result, "tier", None)
            if tier == "simple":
                is_simple_tier = True

        use_recoverable = False

        # Dynamic Parameter Adjustment based on Tier
        # Default values from config
        max_failures = recoverable_cfg.max_failures if recoverable_cfg else 3
        max_retries_before_rollback = (
            recoverable_cfg.max_retries_before_rollback if recoverable_cfg else 1
        )
        max_failures_per_tool = (
            recoverable_cfg.max_failures_per_tool if recoverable_cfg else 2
        )
        enable_filesystem_snapshots = (
            recoverable_cfg.enable_filesystem_snapshots if recoverable_cfg else True
        )

        if is_simple_tier:
            use_recoverable = True  # Force enable for simple tier
            # Simple tier aims for "Clean Success".
            # We allow retries (rollback to checkpoint) to save compute,
            # as the rollback mechanism wipes the failed attempt from history anyway.
            # So the final trajectory remains "perfect".
            if max_retries_before_rollback == 0:
                max_retries_before_rollback = 1
            logger.info(
                f"  ✨ Forcing Recoverable Mode for Phase 0 (Clean Success Strategy)"
            )
        else:
            use_recoverable = config_enabled
            if use_recoverable:
                logger.info(
                    f"  ✨ Using Recoverable Mode (Resilient Level={max_retries_before_rollback})"
                )

        anchor_compliance_info = None

        for attempt in range(max_attempts):
            if use_recoverable:
                logger.info(
                    f"🎯 Step 3: Collecting trajectory with RECOVERABLE mode (attempt {attempt + 1}/{max_attempts})"
                )
            else:
                logger.info(
                    f"🎯 Step 3: Collecting strict trajectory (attempt {attempt + 1}/{max_attempts})"
                )

            # Rollback to S0 state before each attempt (except first)
            if attempt > 0:
                logger.info(f"  🔄 Rolling back to S0 state...")
                await _rollback_to_s0(mcp_client, snapshot_s0, root_str, init_plan)
                logger.info(f"  ✓ Rollback complete")

            # Choose collection method based on config
            if use_recoverable:
                (
                    trajectory,
                    checkpoint_stats,
                ) = await collector.collect_trajectory_recoverable(
                    allowed_tools=sampled_tools,
                    mcp_client=mcp_client,
                    max_steps=task_config.max_steps,
                    system_prompt=system_prompt,
                    workspace_path=workspace_path,
                    target_n_tool_calls=effective_target_n,
                    max_failures=max_failures,
                    max_failures_per_tool=max_failures_per_tool,
                    max_retries_before_rollback=max_retries_before_rollback,
                    enable_filesystem_snapshots=enable_filesystem_snapshots,
                    skill_selections=skill_selections_list,
                    skill_sampler=sampler.skill_sampler if sampler and hasattr(sampler, "skill_sampler") else None,
                    initial_user_message=initial_user_message,
                )
                logger.info(
                    f"  Checkpoint stats: failures={checkpoint_stats.get('total_failures', 0)}, "
                    f"rollbacks={checkpoint_stats.get('rollback_count', 0)}"
                )
            else:
                trajectory = await collector.collect_trajectory(
                    allowed_tools=sampled_tools,
                    mcp_client=mcp_client,
                    max_steps=task_config.max_steps,
                    system_prompt=system_prompt,
                    target_n_tool_calls=effective_target_n,
                    skill_selections=skill_selections_list,
                    skill_sampler=sampler.skill_sampler if sampler and hasattr(sampler, "skill_sampler") else None,
                    initial_user_message=initial_user_message,
                )

            logger.info(
                f"  Trajectory: status={trajectory.status.value}, "
                f"successful_tool_calls={trajectory.num_successful_tool_calls}/{effective_target_n}"
            )

            pre_retention_tool_calls = copy.deepcopy(
                getattr(trajectory, "tool_calls", []) if trajectory is not None else []
            )
            retention_applied = False

            if efficiency_monitor is not None and trajectory.token_usage:
                efficiency_monitor.record_token_usage(
                    trajectory.token_usage.get("prompt", 0),
                    trajectory.token_usage.get("completion", 0),
                )

            # Record granular failure stats for quality diagnostics.
            _record_iteration_failures(
                storage=storage,
                trajectory=trajectory,
                checkpoint_stats=checkpoint_stats,
                episode_id=f"{mcp_server_name}_{iteration:06d}_attempt_{attempt + 1}",
            )

            # Prune failure-only tool traces (tools with failed calls but no successful call).
            # Keep failure traces only when that tool also succeeds later (error-recovery value).
            trajectory, prune_stats = collector.prune_failure_only_tools(trajectory)
            removed_failed_calls = int(prune_stats.get("removed_failed_calls_count", 0) or 0)
            if removed_failed_calls > 0:
                retention_applied = True
                logger.info(
                    "  🧹 Pruned %d failure-only tool calls (tools=%s)",
                    removed_failed_calls,
                    prune_stats.get("removed_failure_only_tools", []),
                )

            # If episode ended with an error tail, trim back to last successful call.
            # This avoids wasting a full re-attempt when a nearly-complete trace is salvageable.
            if (
                trajectory is not None
                and trajectory.status != EpisodeStatus.SUCCESS
                and trajectory.num_successful_tool_calls >= 1
            ):
                trajectory, rollback_stats = collector.rollback_to_last_successful_prefix(
                    trajectory
                )
                if rollback_stats.get("applied"):
                    retention_applied = True
                    logger.info(
                        "  🔧 Rolled back to last successful tool prefix: removed_tail=%s, new_success_calls=%s",
                        rollback_stats.get("removed_trailing_calls_count", 0),
                        rollback_stats.get("new_num_successful_tool_calls", trajectory.num_successful_tool_calls),
                    )
                    if checkpoint_stats is not None:
                        checkpoint_stats.setdefault("salvage", {})
                        checkpoint_stats["salvage"]["rollback_to_last_success_prefix"] = rollback_stats

            # Apply hard filters
            hard_filter_result = apply_hard_filters(trajectory)
            if not hard_filter_result.passed:
                logger.warning(
                    f"  ✗ Hard filter failed: {hard_filter_result.reason}"
                )
                _save_filtered_if_enabled(
                    reason=f"Attempt {attempt + 1}: hard filter failed: {hard_filter_result.reason}",
                    filter_stage="hard_filter",
                    trajectory_obj=trajectory,
                    attempt=attempt + 1,
                )
                last_filter_reason = hard_filter_result.reason
                continue  # Try again

            # Take S1 snapshot and compute diff using adapter (if available)
            if snapshot_provider is not None and "diff_comparator" in adapters:
                snapshot_s1 = await snapshot_provider.create_snapshot(root_str)

                diff_comparator_class = adapters["diff_comparator"]
                diff_comparator = diff_comparator_class()
                diff = diff_comparator.diff(snapshot_s0, snapshot_s1)
                logger.info(f"  Diff: {diff.get_change_summary()}")
            elif hasattr(mcp_client, "admin_request") and isinstance(snapshot_s0, dict):
                # Benchmark world: compare state hashes (generic — adapts to any world)
                try:
                    state_s1 = await mcp_client.admin_request("/admin/state")

                    s0_state = _world_state_hash_view(snapshot_s0)
                    s1_state = _world_state_hash_view(state_s1)
                    state_changed = s0_state != s1_state

                    # Extract any *_hash keys for concise logging (works for both
                    # database-backed worlds and Terminal-Bench's
                    # workspace_hash/command_history_hash)
                    hash_label = (
                        f"S0={s0_state}, S1={s1_state}"
                        if s0_state
                        else f"S0_keys={sorted(s0_state.keys())}, S1_keys={sorted(s1_state.keys())}"
                    )

                    diff = _WorldStateDiff(changed=state_changed, s0=snapshot_s0, s1=state_s1)
                    logger.info(
                        f"  World state diff: {'CHANGED' if state_changed else 'UNCHANGED'} "
                        f"({hash_label})"
                    )
                except Exception as e:
                    diff = None
                    logger.warning(f"  Could not compute world state diff: {e}")
            else:
                # No state tracking available at all
                diff = None
                logger.info("  Diff: N/A (no state tracking available)")

            # Determine task type (mutation vs retrieval)
            resolved_mutating_tools = (
                resolved_tool_metadata.get("mutating_tools")
                if resolved_tool_metadata
                else None
            )
            task_type = determine_task_type(
                diff,
                trajectory.tool_calls,
                read_only_tools_priority=read_only_tools_priority,
                mutating_tools=resolved_mutating_tools,
            )
            logger.info(f"  Task type: {task_type.value}")

            # Build retrieval spec if retrieval mode
            if task_type == TaskType.RETRIEVAL:
                retrieval_spec = build_retrieval_spec(
                    trajectory.tool_calls,
                    root_str,
                    language=language,
                    read_only_tools_priority=read_only_tools_priority,
                )
                logger.info(f"  Retrieval spec: {retrieval_spec.get_summary()}")

            # Apply soft filters (dual-mode aware)
            soft_filter_result = apply_soft_filters(
                trajectory,
                diff,
                min_steps=trajs2data_cfg.filters.min_steps,
                min_changes=trajs2data_cfg.filters.min_changes,
                max_changes=trajs2data_cfg.filters.max_changes,
                max_failure_rate=trajs2data_cfg.filters.max_failure_rate,
                task_type=task_type,
                retrieval_spec=retrieval_spec,
            )

            if not soft_filter_result.passed:
                logger.warning(
                    f"  ✗ Soft filter failed: {soft_filter_result.reason}"
                )
                _save_filtered_if_enabled(
                    reason=f"Attempt {attempt + 1}: soft filter failed: {soft_filter_result.reason}",
                    filter_stage="soft_filter",
                    trajectory_obj=trajectory,
                    attempt=attempt + 1,
                )
                last_filter_reason = soft_filter_result.reason
                continue  # Try again

            # Verify anchor constraints (if using sampler)
            # Relaxed Filtering (PRD 3.1): Accept valid trajectories even if anchors are missed.
            if anchor_compliance_info is None:
                anchor_compliance_info = {}
            if sampling_result and sampling_result.anchors and sampler:
                tools_called = [
                    tc.tool_name for tc in trajectory.tool_calls if tc.success
                ]
                anchors_passed, missing_anchors = sampler.verify_anchors_called(
                    sampling_result, tools_called
                )
                if not anchors_passed:
                    logger.warning(
                        f"  ⚠️ Anchor constraint failed: missing {missing_anchors} (Relaxed Filtering: Keeping trajectory)"
                    )
                    anchor_compliance_info = {
                        "anchor_compliance": False,
                        "missing_anchors": missing_anchors,
                    }
                else:
                    anchor_compliance_info = {"anchor_compliance": True}

            anchor_usage_info = {}
            if sampling_result:
                exposed_anchor_names = list(
                    dict.fromkeys(
                        list(getattr(sampling_result, "anchor_tools_used", []) or [])
                        + list(getattr(sampling_result, "anchors", []) or [])
                    )
                )
                anchor_usage_info = build_anchor_usage_metadata(
                    exposed_anchors=exposed_anchor_names,
                    required_anchors=getattr(sampling_result, "anchors", []) or [],
                    pre_retention_tool_calls=pre_retention_tool_calls,
                    final_tool_calls=getattr(trajectory, "tool_calls", []) or [],
                    retention_applied=retention_applied,
                )

            # SUCCESS - all filters passed
            logger.info(f"  ✓ All filters passed on attempt {attempt + 1}")
            attempt_success = True
            break

        # If all attempts failed, save as filtered and return
        if not attempt_success:
            logger.warning(f"  ✗ All {max_attempts} attempts failed")
            _save_filtered_if_enabled(
                reason=f"All {max_attempts} attempts failed. Last reason: {last_filter_reason}",
                filter_stage="all_attempts_failed",
                trajectory_obj=trajectory,
            )
            # Record filtered attempt in efficiency monitor
            if efficiency_monitor is not None:
                efficiency_monitor.record_attempt(
                    saved=False, filtered=True, deduped=False
                )
            return False

        # ============================================================
        # STEP 4: Optional Deferred Synthesis (Collection-Only Mode)
        # ============================================================
        if not synthesis_in_collection:
            replay_cfg = getattr(trajs2data_cfg, "replay_verification", None)
            if replay_cfg and replay_cfg.enabled:
                logger.warning(
                    "replay_verification.enabled is ignored when synthesis_in_collection=False; "
                    "run replay verification in collection mode or add an offline replay stage."
                )
            if getattr(storage, "dedup_enabled", False):
                logger.warning(
                    "Deduplication is not applied in trajs2data_raw save mode; "
                    "perform dedup in data_synthesis if needed."
                )
            logger.info("🧾 Step 4: Deferring synthesis to data_synthesis (raw save mode)")

            # Build deterministic intent/retrieval specs for deferred LLM synthesis
            deferred_intent_spec = None
            if task_type == TaskType.MUTATION and trajectory is not None and diff is not None:
                try:
                    deferred_intent_spec = build_intent_spec(
                        diff, trajectory.tool_calls, root_str, task_config=task_config
                    )
                except Exception as e:
                    logger.warning(f"Failed to build deferred intent_spec: {e}")

            state_evidence_payload = build_state_evidence(diff)
            experience_context = _build_experience_context(
                task_config=task_config,
                selected_env=selected_env,
                reset_meta=_episode_reset_meta,
                episode_world_context=episode_world_context,
                sampling_result=sampling_result,
                tool_names=tool_names,
                task_type=task_type,
                retrieval_spec=retrieval_spec,
                intent_spec=deferred_intent_spec,
                state_evidence=state_evidence_payload,
                anchor_usage=anchor_usage_info,
                trajectory=trajectory,
            )
            quality_signals = _build_quality_signals(
                trajectory=trajectory,
                state_evidence=state_evidence_payload,
                anchor_usage=anchor_usage_info,
                sampling_result=sampling_result,
                target_n=effective_target_n,
                checkpoint_stats=checkpoint_stats,
            )

            raw_context = {
                "schema_version": "trajs2data_raw_v1",
                "synthesis_deferred": True,
                "world_context": build_world_context(
                    task_config=task_config,
                    primary_server=primary_server,
                    prompt_domain=prompt_domain,
                    output_namespace=output_namespace,
                    reset_strategy=reset_strategy,
                    state_strategy=state_strategy,
                    reset_metadata={
                        "init_summary": init_summary,
                        "episode_reset_meta": _episode_reset_meta,
                    },
                    world_context_override=episode_world_context,
                ),
                "task_domain": getattr(task_config, "task_type", "filesystem"),
                "task_type": task_type.value if task_type else None,
                "mcp_server": mcp_server_name,
                "language": language,
                "collection_task_objective": _extract_stated_objective(trajectory),
                "filesystem_root": root_str,
                "world_root": root_str,
                "episode_seed": episode_seed,
                "init_summary": init_summary,
                "init_ops": _init_plan_to_operations(init_plan),
                "tools_subset": sampled_tools,
                "tools_allowed": tool_names,
                "diff_summary": diff.get_change_summary() if diff else None,
                "state_evidence": state_evidence_payload,
                "quality_signals": quality_signals,
                "tool_exposure": {
                    "stage": sampling_result.stage if sampling_result else None,
                    "tier": sampling_result.tier if sampling_result else None,
                    "phase": sampling_result.phase if sampling_result else None,
                    "visible_tools": tool_names,
                    "base_tools": (
                        sampling_result.base_tools_used if sampling_result else []
                    ),
                    "anchor_tools": (
                        sampling_result.anchor_tools_used if sampling_result else []
                    ),
                    "required_anchors": (
                        sampling_result.anchors if sampling_result else []
                    ),
                    "target_n": effective_target_n,
                },
                "anchor_usage": anchor_usage_info,
                "experience_context": experience_context,
                "intent_spec": (
                    deferred_intent_spec.to_dict()
                    if deferred_intent_spec is not None
                    else None
                ),
                "retrieval_spec": (
                    retrieval_spec.to_dict() if retrieval_spec is not None else None
                ),
                "sampling_result": (
                    sampling_result.to_metadata() if sampling_result else None
                ),
                "checkpoint_stats": checkpoint_stats,
                "task_config": (
                    task_config.model_dump()
                    if hasattr(task_config, "model_dump")
                    else str(task_config)
                ),
            }

            metadata_extra = {
                "artifact_namespace": getattr(task_config, "artifact_namespace", ""),
                "task_type": task_config.task_type,
                "required_servers": task_config.required_servers,
                "primary_server": primary_server,
                "seed": episode_seed,
                "type": task_type.value if task_type else "unknown",
                "n_target": effective_target_n,
                "n_actual": trajectory.num_successful_tool_calls if trajectory else 0,
                "n_tools_sampled": len(sampled_tools),
                "tools_allowed": tool_names,
                "size_profile": getattr(task_config, "size_profile", "N/A"),
                "diff_summary": diff.get_change_summary() if diff else "N/A",
                "state_evidence": state_evidence_payload,
                "quality_signals": quality_signals,
                "experience_context": experience_context,
                "collection_mode": "strict",
                "synthesis_in_collection": False,
                "prompt_domain": prompt_domain,
                "output_namespace": output_namespace,
                "data_source": _build_data_source_metadata(
                    selected_env=selected_env,
                    reset_meta=_episode_reset_meta,
                    init_summary=init_summary,
                ),
                "world_context": build_world_context(
                    task_config=task_config,
                    primary_server=primary_server,
                    prompt_domain=prompt_domain,
                    output_namespace=output_namespace,
                    reset_strategy=reset_strategy,
                    state_strategy=state_strategy,
                    reset_metadata={
                        "init_summary": init_summary,
                        "episode_reset_meta": _episode_reset_meta,
                    },
                    world_context_override=episode_world_context,
                ),
                "anchor_usage": anchor_usage_info,
            }
            if checkpoint_stats:
                metadata_extra["checkpoint_stats"] = checkpoint_stats
                metadata_extra["collection_mode"] = "recoverable"
            if init_summary:
                metadata_extra["init_summary"] = init_summary
                metadata_extra["init_mode"] = init_summary.get(
                    "init_mode", getattr(task_config, "init_mode", "random")
                )
            if sampling_result:
                metadata_extra.update(sampling_result.to_metadata())
            if anchor_compliance_info:
                metadata_extra.update(anchor_compliance_info)

            raw_saved_path = storage.save_trajs2data_raw_episode(
                trajectory=_to_serializable(trajectory.to_dict()),
                raw_context=_to_serializable(raw_context),
                mcp_server_name=mcp_server_name,
                iteration=iteration,
                metadata_extra=_to_serializable(metadata_extra),
            )

            if raw_saved_path:
                logger.info(f"  ✓ Raw episode saved to: {raw_saved_path}")

                replay_synthesis_cfg = getattr(trajs2data_cfg, "replay_synthesis", None)
                if replay_synthesis_cfg and getattr(replay_synthesis_cfg, "enabled", False):
                    logger.info("🔁 Step 4b: Running replay_synthesis from raw exploration episode")
                    try:
                        runner_cfg = ReplaySynthesisConfig(
                            enabled=True,
                            max_problem_candidates=getattr(replay_synthesis_cfg, "max_problem_candidates", 3),
                            max_replay_attempts=getattr(replay_synthesis_cfg, "max_replay_attempts", 2),
                            min_quality_tier=getattr(replay_synthesis_cfg, "min_quality_tier", "acceptable"),
                            tool_sequence_selection=getattr(replay_synthesis_cfg, "tool_sequence_selection", "heuristic"),
                            verify_final_state=getattr(replay_synthesis_cfg, "verify_final_state", True),
                            save_failed_replays=getattr(replay_synthesis_cfg, "save_failed_replays", True),
                            harness_mode=getattr(replay_synthesis_cfg, "harness_mode", "full"),
                            harness_max_retries_per_step=getattr(replay_synthesis_cfg, "harness_max_retries_per_step", 2),
                            harness_model=getattr(replay_synthesis_cfg, "harness_model", "trajectory_collection"),
                            harness_fallback_threshold=getattr(replay_synthesis_cfg, "harness_fallback_threshold", 0.5),
                            preserve_failure_recovery_chains=getattr(replay_synthesis_cfg, "preserve_failure_recovery_chains", True),
                            dependency_relevance_filter=getattr(replay_synthesis_cfg, "dependency_relevance_filter", True),
                            llm_problem_synthesis=getattr(replay_synthesis_cfg, "llm_problem_synthesis", True),
                            max_dependency_distance=getattr(replay_synthesis_cfg, "max_dependency_distance", 5),
                            polish_enabled=getattr(replay_synthesis_cfg, "polish_enabled", True),
                            polish_model=getattr(replay_synthesis_cfg, "polish_model", "judge_model"),
                            enable_quality_judge=getattr(replay_synthesis_cfg, "enable_quality_judge", True),
                            judge_hard_weight=getattr(replay_synthesis_cfg, "judge_hard_weight", 0.70),
                            judge_soft_weight=getattr(replay_synthesis_cfg, "judge_soft_weight", 0.20),
                            judge_dual_bonus=getattr(replay_synthesis_cfg, "judge_dual_bonus", 0.10),
                            judge_threshold_high=getattr(replay_synthesis_cfg, "judge_threshold_high", 0.85),
                            judge_threshold_acceptable=getattr(replay_synthesis_cfg, "judge_threshold_acceptable", 0.70),
                        )
                        replay_runner = ReplaySynthesisRunner(runner_cfg)
                        if state_strategy == "admin_state_hash":
                            await restore_admin_replay_s0(
                                mcp_client=mcp_client,
                                original_reset_meta=_episode_reset_meta,
                                fallback_seed=iteration,
                            )
                        else:
                            await _rollback_to_s0(mcp_client, snapshot_s0, root_str, init_plan)

                        # Resolve model configs for replay pipeline
                        harness_model_config = None
                        if runner_cfg.harness_mode != "disabled":
                            try:
                                if runner_cfg.harness_model == "nl_rewrite":
                                    harness_model_config = config.maas.models.nl_rewrite
                                else:
                                    harness_model_config = config.maas.models.trajectory_collection
                            except Exception:
                                harness_model_config = None

                        # Problem synthesis model (independent of harness mode)
                        problem_synthesis_model_config = None
                        if runner_cfg.llm_problem_synthesis:
                            try:
                                problem_synthesis_model_config = config.maas.models.nl_rewrite
                            except Exception:
                                problem_synthesis_model_config = None

                        polish_model_config = None
                        if runner_cfg.polish_enabled:
                            try:
                                if runner_cfg.polish_model == "nl_rewrite":
                                    polish_model_config = config.maas.models.nl_rewrite
                                else:
                                    polish_model_config = config.maas.models.judge
                            except Exception:
                                polish_model_config = None

                        judge_model_config = None
                        if runner_cfg.enable_quality_judge:
                            try:
                                judge_model_config = config.maas.models.judge
                            except Exception:
                                judge_model_config = None

                        replay_world_context = _build_episode_world_context(task_config, selected_env)

                        replay_result = await replay_runner.run(
                            trajectory=trajectory,
                            task_type=task_type.value if task_type else "retrieval",
                            state_evidence=state_evidence_payload,
                            retrieval_spec=retrieval_spec,
                            mcp_client=mcp_client,
                            tools=sampled_tools,
                            original_s1=(diff.s1 if hasattr(diff, "s1") else None),
                            language=language,
                            maas_client=maas_client,
                            model_config=problem_synthesis_model_config,
                            harness_model_config=harness_model_config,
                            polish_model_config=polish_model_config,
                            judge_model_config=judge_model_config,
                            world_context=replay_world_context,
                            read_only_tools=read_only_tools,
                        )
                        replay_payload = {
                            "accepted": replay_result.accepted,
                            "rejected_reason": replay_result.rejected_reason,
                            "problem": (
                                replay_result.problem_spec.__dict__
                                if replay_result.problem_spec is not None
                                else {}
                            ),
                            "trajectory": {
                                "messages": replay_result.messages,
                                "tool_calls": (
                                    replay_result.selection.selected_calls
                                    if replay_result.selection is not None
                                    else []
                                ),
                                "num_steps": (
                                    len(replay_result.selection.selected_calls)
                                    if replay_result.selection is not None
                                    else 0
                                ),
                                "num_successful_tool_calls": (
                                    len(replay_result.selection.selected_calls)
                                    if replay_result.selection is not None
                                    else 0
                                ),
                                "status": "success" if replay_result.accepted else "rejected",
                            },
                            "replay_context": {
                                "source_raw_episode": str(raw_saved_path),
                                "selected_tool_sequence": (
                                    replay_result.selection.selected_calls
                                    if replay_result.selection is not None
                                    else []
                                ),
                                "dropped_calls": (
                                    replay_result.selection.dropped_calls
                                    if replay_result.selection is not None
                                    else []
                                ),
                                "evidence_summary": (
                                    replay_result.problem_spec.evidence_summary
                                    if replay_result.problem_spec is not None
                                    else ""
                                ),
                                "judge": (
                                    replay_result.problem_spec.judge
                                    if replay_result.problem_spec is not None
                                    else {}
                                ),
                            },
                            "verification": replay_result.verification,
                            "review_record": replay_result.review_record,
                        }
                        replay_saved_path = storage.save_trajs2data_replay_synthesis_episode(
                            replay_payload=_to_serializable(replay_payload),
                            mcp_server_name=mcp_server_name,
                            iteration=iteration,
                            metadata_extra=_to_serializable({
                                "output_namespace": output_namespace,
                                "source_raw_episode": str(raw_saved_path),
                                "task_type": task_type.value if task_type else None,
                                "synthesis_in_collection": False,
                                "collection_mode": "replay_synthesis",
                            }),
                            min_quality_tier=runner_cfg.min_quality_tier,
                        )
                        logger.info(
                            "  %s Replay synthesis episode saved to: %s",
                            "✓" if replay_result.accepted else "✗",
                            replay_saved_path,
                        )
                    except Exception as e:
                        logger.warning("Replay synthesis failed for %s: %s", raw_saved_path, e)

                # Update coverage tracker AFTER successful save
                if coverage_tracker and trajectory is not None:
                    try:
                        successful_tools = [
                            tc.tool_name for tc in trajectory.tool_calls if tc.success
                        ]
                        episode_id = f"trajs2data_{iteration:06d}"
                        coverage_tracker.record_episode_tools(
                            tool_names, successful_tools, episode_id
                        )
                        coverage_tracker.save()
                    except Exception as e:
                        logger.warning(f"Coverage tracker update failed (non-fatal): {e}")

                if efficiency_monitor is not None and trajectory is not None:
                    is_salvaged = bool(
                        trajectory.abort_reason and "Salvaged" in trajectory.abort_reason
                    )
                    efficiency_monitor.record_attempt(
                        saved=True, filtered=False, deduped=False, salvaged=is_salvaged
                    )
                    efficiency_monitor.check_and_reset_on_improvement()

                # Extract experience in raw mode as well (deferred synthesis).
                if experience_manager is not None and trajectory is not None:
                    try:
                        successful_tools = _safe_tool_names_from_trajectory(trajectory)
                        experience_metadata = {
                            "episode_id": f"trajs2data_{iteration:06d}",
                            "output_path": str(raw_saved_path),
                            "pipeline_mode": "trajs2data_raw",
                            "task_type": task_type.value if task_type else None,
                            "stage": sampling_result.stage if sampling_result else None,
                            "tier": sampling_result.tier if sampling_result else None,
                            "phase": sampling_result.phase if sampling_result else None,
                            "world_domain": experience_context.get("world_domain"),
                            "data_source": metadata_extra.get("data_source"),
                            "output_namespace": output_namespace,
                        }
                        fallback_problem = {
                            "problem": (
                                "Summarize the reusable operational pattern from "
                                f"an executed {task_type.value if task_type else 'unknown'} "
                                f"trajectory in {experience_context.get('world_domain', 'an executable world')} "
                                f"using tools: {', '.join(successful_tools[:8])}."
                            ),
                            "experience_context": experience_context,
                            "experience_metadata": experience_metadata,
                        }

                        experience_manager.schedule_extraction(
                            trajectory=trajectory,
                            problem=fallback_problem,
                            metadata=experience_metadata,
                        )
                    except Exception as exp_err:
                        logger.warning(
                            f"Failed to schedule experience extraction in raw mode: {exp_err}"
                        )

                cleanup_success = True
                return True

            if efficiency_monitor is not None:
                efficiency_monitor.record_attempt(
                    saved=False, filtered=False, deduped=False
                )
            _save_filtered_if_enabled(
                reason="Raw save failed: storage.save_trajs2data_raw_episode returned None",
                filter_stage="raw_save_failed",
                trajectory_obj=trajectory,
            )
            return False

        # ============================================================
        # STEP 4: Synthesize Problem (Dual-Mode)
        # ============================================================
        logger.info(f"📝 Step 4: Synthesizing problem ({task_type.value} mode)")

        # Get NL rewrite model config
        nl_model_config = config.get_nl_rewrite_model_config()

        # Get init operations
        init_ops = _init_plan_to_operations(init_plan)

        final_assistant_answer = None

        if task_type == TaskType.MUTATION:
            if diff is None or trajectory is None:
                logger.error(
                    "Cannot synthesize mutation: diff or trajectory is None"
                )
                _save_filtered_if_enabled(
                    reason="Cannot synthesize mutation: diff or trajectory is None",
                    filter_stage="synthesis_precondition_mutation",
                    trajectory_obj=trajectory,
                )
                return False

            # Use generalized intent builder
            intent_spec = build_intent_spec(
                diff, trajectory.tool_calls, root_str, task_config=task_config
            )
            logger.info(f"  Intent: {intent_spec.to_dict()}")

            problem_json = await rewrite_to_problem_json(
                intent_spec=intent_spec,
                tools_subset=sampled_tools,
                init_ops=init_ops,
                mcp_server=mcp_server_name,
                maas_client=maas_client,
                model_config=nl_model_config,
                root=root_str,
                language=language,
                self_questioning_config=getattr(
                    trajs2data_cfg, "self_questioning", None
                ),
                embedding_provider=embedding_provider,
                prompt_domain=prompt_domain,
            )
            problem_json["task_type"] = TaskType.MUTATION.value

        else:
            if trajectory is None:
                logger.error("Cannot synthesize retrieval: trajectory is None")
                _save_filtered_if_enabled(
                    reason="Cannot synthesize retrieval: trajectory is None",
                    filter_stage="synthesis_precondition_retrieval",
                    trajectory_obj=trajectory,
                )
                return False
            if retrieval_spec is None:
                retrieval_spec = build_retrieval_spec(
                    trajectory.tool_calls, root_str, language=language
                )

            logger.info(f"  Retrieval spec: {retrieval_spec.get_summary()}")

            problem_json = await rewrite_retrieval_to_problem_json(
                retrieval_spec=retrieval_spec,
                tools_subset=sampled_tools,
                init_ops=init_ops,
                mcp_server=mcp_server_name,
                maas_client=maas_client,
                model_config=nl_model_config,
                root=root_str,
                language=language,
                prompt_domain=prompt_domain,
            )

            # Final assistant answer for retrieval mode
            final_assistant_answer = problem_json.get("reference_answer", "")

        logger.info(f"  ✓ Problem: {problem_json['problem'][:80]}...")

        # ============================================================
        # STEP 4.25: Hindsight Reasoning (God mode rewrite)
        # ============================================================
        hindsight_cfg = getattr(trajs2data_cfg, "hindsight", None)
        original_trajectory_copy = None  # Initialize variable

        if (
            hindsight_cfg
            and hindsight_cfg.enabled
            and hindsight_cfg.rewrite_thoughts
            and trajectory is not None
        ):
            logger.info(f"🧠 Step 4.25: Rewriting trajectory thoughts (Hindsight)")
            # Create a copy of the original trajectory before modification
            original_trajectory_copy = copy.deepcopy(trajectory.to_dict())

            try:
                trajectory = await rewrite_trajectory_thoughts(
                    trajectory=trajectory,
                    problem=problem_json,
                    maas_client=maas_client,
                    model_config=config.get_nl_rewrite_model_config(),
                    language=language,
                )
                logger.info("  ✓ Thoughts rewritten successfully")
            except Exception as e:
                logger.error(f"  ✗ Hindsight rewriting failed: {e}")
                # Continue without rewriting, don't fail the whole episode

        # ============================================================
        # STEP 4.5: Replay Verification (Optional)
        # ============================================================
        replay_cfg = getattr(trajs2data_cfg, "replay_verification", None)
        replay_verification_result = None

        if (
            replay_cfg
            and replay_cfg.enabled
            and task_type == TaskType.MUTATION
            and diff is not None
            and trajectory is not None
        ):
            logger.info(f"🔄 Step 4.5: Replay verification")

            from data_collection.replay_verifier import ReplayVerifier, ReplayResult

            verifier = ReplayVerifier(
                collector=collector,
                similarity_threshold=replay_cfg.similarity_threshold,
                max_replay_steps=replay_cfg.max_replay_steps,
            )

            replay_verification_result = await verifier.verify(
                problem_json=problem_json,
                original_trajectory=trajectory.to_dict(),
                original_diff=diff,
                mcp_client=mcp_client,
                workspace_path=workspace_path,
                init_plan=init_plan,
            )

            logger.info(
                f"  Replay result: {replay_verification_result.result.value}, "
                f"similarity: {replay_verification_result.similarity_score:.2f}"
            )

            # If fail_on_mismatch is enabled and verification failed, skip saving
            if (
                replay_cfg.fail_on_mismatch
                and replay_verification_result.result
                not in [ReplayResult.PASSED, ReplayResult.SKIPPED]
            ):
                logger.warning(f"  ✗ Replay verification failed, skipping save")
                _save_filtered_if_enabled(
                    reason=(
                        "Replay verification failed: "
                        f"{replay_verification_result.result.value}"
                    ),
                    filter_stage="replay_verification",
                    trajectory_obj=trajectory,
                )
                return False

        # ============================================================
        # STEP 5: Save & Update Coverage
        # ============================================================
        logger.info(f"💾 Step 5: Saving and updating coverage")

        state_evidence_payload = build_state_evidence(diff)
        synthesis_experience_context = _build_experience_context(
            task_config=task_config,
            selected_env=selected_env,
            reset_meta=_episode_reset_meta,
            episode_world_context=episode_world_context,
            sampling_result=sampling_result,
            tool_names=tool_names,
            task_type=task_type,
            retrieval_spec=retrieval_spec,
            state_evidence=state_evidence_payload,
            anchor_usage=anchor_usage_info,
            trajectory=trajectory,
        )
        quality_signals = _build_quality_signals(
            trajectory=trajectory,
            state_evidence=state_evidence_payload,
            anchor_usage=anchor_usage_info,
            sampling_result=sampling_result,
            target_n=effective_target_n,
            checkpoint_stats=checkpoint_stats,
        )

        # Build rich metadata
        metadata_extra = {
            "artifact_namespace": getattr(task_config, "artifact_namespace", ""),
            "task_type": task_config.task_type,
            "required_servers": task_config.required_servers,
            "primary_server": primary_server,
            "seed": episode_seed,
            "type": task_type.value,
            "n_target": effective_target_n,
            "n_actual": trajectory.num_successful_tool_calls,
            "n_tools_sampled": len(sampled_tools),
            "tools_allowed": tool_names,
            "size_profile": getattr(task_config, "size_profile", "N/A"),
            "diff_summary": diff.get_change_summary() if diff else "N/A",
            "state_evidence": state_evidence_payload,
            "quality_signals": quality_signals,
            "experience_context": synthesis_experience_context,
            "data_source": _build_data_source_metadata(
                selected_env=selected_env,
                reset_meta=_episode_reset_meta,
                init_summary=init_summary,
            ),
            "world_context": build_world_context(
                task_config=task_config,
                primary_server=primary_server,
                prompt_domain=prompt_domain,
                output_namespace=output_namespace,
                reset_strategy=reset_strategy,
                state_strategy=state_strategy,
                reset_metadata={
                    "init_summary": init_summary,
                    "episode_reset_meta": _episode_reset_meta,
                },
                world_context_override=episode_world_context,
            ),
            "anchor_usage": anchor_usage_info,
        }
        if init_summary:
            metadata_extra["init_summary"] = init_summary
            metadata_extra["init_mode"] = init_summary.get(
                "init_mode", getattr(task_config, "init_mode", "random")
            )

        # Add checkpoint stats if using recoverable mode
        if checkpoint_stats:
            metadata_extra["checkpoint_stats"] = checkpoint_stats
            metadata_extra["collection_mode"] = "recoverable"
        else:
            metadata_extra["collection_mode"] = "strict"

        # Check if trajectory was salvaged
        if "salvaged" in (trajectory.abort_reason or "").lower():
            metadata_extra["salvaged"] = True
            storage.record_salvaged_episode(
                original_target_n=effective_target_n,
                actual_steps=trajectory.num_successful_tool_calls,
                reason="max_failures",
            )

        # Prepare trajectory dict for saving
        trajectory_dict = trajectory.to_dict()
        if original_trajectory_copy:
            trajectory_dict["original_trajectory"] = original_trajectory_copy

        # Add phase/sampler metadata if available
        if sampling_result:
            metadata_extra.update(sampling_result.to_metadata())

        # Add base_tools version reference
        if tool_curriculum_cfg:
            metadata_extra["base_tools_version"] = "v1"
            metadata_extra["base_tools"] = list((resolved_tool_metadata or {}).get("base_tools") or tool_curriculum_cfg.base_tools or [])
            metadata_extra["read_only_tools"] = list(read_only_tools)
            metadata_extra["read_only_tools_priority"] = list(read_only_tools_priority)
            metadata_extra["prompt_domain"] = prompt_domain
            metadata_extra["output_namespace"] = output_namespace

        # Add anchor compliance info
        if "anchor_compliance_info" in locals():
            metadata_extra.update(anchor_compliance_info)

        # Add replay verification result if available
        if replay_verification_result:
            metadata_extra["replay_verification"] = (
                replay_verification_result.to_dict()
            )

        # Save to disk
        saved_path = storage.save_trajs2data_trajectory(
            trajectory=trajectory_dict,
            problem_data=problem_json,
            mcp_server_name=mcp_server_name,
            iteration=iteration,
            metadata_extra=metadata_extra,
            final_assistant_answer=final_assistant_answer,
        )

        if saved_path:
            logger.info(f"  ✓ Saved to: {saved_path}")

            # Update coverage tracker AFTER successful save (avoid inflating stats on dedup)
            if coverage_tracker:
                try:
                    successful_tools = [
                        tc.tool_name for tc in trajectory.tool_calls if tc.success
                    ]
                    episode_id = f"trajs2data_{iteration:06d}"
                    coverage_tracker.record_episode_tools(
                        tool_names, successful_tools, episode_id
                    )
                    coverage_tracker.save()
                except Exception as e:
                    logger.warning(f"Coverage tracker update failed (non-fatal): {e}")

            # Record successful save in efficiency monitor
            if efficiency_monitor is not None:
                is_salvaged = (
                    trajectory
                    and trajectory.abort_reason
                    and "Salvaged" in trajectory.abort_reason
                )
                efficiency_monitor.record_attempt(
                    saved=True, filtered=False, deduped=False, salvaged=is_salvaged
                )
                efficiency_monitor.check_and_reset_on_improvement()

            # Extract experience from successful episode (PRD 4.7)
            if experience_manager is not None and trajectory is not None:
                try:
                    experience_metadata = {
                        "episode_id": f"trajs2data_{iteration:06d}",
                        "output_path": str(saved_path),
                        "pipeline_mode": "trajs2data",
                        "task_type": task_type.value if task_type else None,
                        "stage": sampling_result.stage if sampling_result else None,
                        "tier": sampling_result.tier if sampling_result else None,
                        "phase": sampling_result.phase if sampling_result else None,
                        "world_domain": synthesis_experience_context.get("world_domain"),
                        "data_source": metadata_extra.get("data_source"),
                        "output_namespace": output_namespace,
                    }
                    problem_for_experience = dict(problem_json)
                    problem_for_experience["experience_context"] = synthesis_experience_context
                    problem_for_experience["experience_metadata"] = experience_metadata
                    experience_manager.schedule_extraction(
                        trajectory=trajectory,
                        problem=problem_for_experience,
                        metadata=experience_metadata,
                    )
                except Exception as exp_err:
                    logger.warning(f"Failed to extract experience: {exp_err}")
        else:
            logger.info(f"  ⊘ Deduplicated (same problem with similar trajectory)")
            # Record dedup in efficiency monitor (counts as not saved)
            if efficiency_monitor is not None:
                efficiency_monitor.record_attempt(
                    saved=False, filtered=False, deduped=True
                )

        cleanup_success = True
        return True

    except Exception as e:
        logger.error(f"Iteration {iteration} failed with error: {e}", exc_info=True)
        filtered_trajectory = {
            "status": "error",
            "abort_reason": "runtime_exception_before_trajectory",
            "num_steps": 0,
            "tool_calls": [],
            "messages": [],
            "error": {
                "type": type(e).__name__,
                "message": str(e),
            },
        }
        trajectory_obj = locals().get("trajectory", None)
        if trajectory_obj is not None:
            filtered_trajectory = trajectory_obj
        _save_filtered_if_enabled(
            reason=f"Runtime exception: {type(e).__name__}: {e}",
            filter_stage="runtime_exception",
            trajectory_obj=filtered_trajectory,
        )
        return False

    finally:
        # Only cleanup MCP clients if we started them (not pre-started)
        if owns_servers and "mcp_clients" in locals():
            for server_name, client in mcp_clients.items():
                try:
                    logger.debug(f"Cleaning up MCP client: {server_name}")
                    await _cleanup_world_session(client, server_name, logger)
                    await client.disconnect()
                except Exception as e:
                    logger.warning(f"Failed to cleanup MCP client {server_name}: {e}")
                finally:
                    server_manager.unregister_server(server_name, iteration)

        # Only cleanup workspace if we created it (not reused)
        if reuse_workspace is None:
            cleanup_needed = (
                config.local.cleanup_on_success
                if cleanup_success
                else config.local.cleanup_on_failure
            )

            if workspace_path and workspace_path.exists() and cleanup_needed:
                try:
                    shutil.rmtree(workspace_path)
                    logger.debug(f"Cleaned up workspace: {workspace_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup workspace {workspace_path}: {e}")


async def _rollback_to_s0(mcp_client, snapshot_s0, root_str: str, init_plan=None):
    """Rollback environment to S0 state by recreating from snapshot/init plan.

    This rollback:
    1. Removes all files/directories in the workspace
    2. Re-executes the init plan to restore S0 state

    Args:
        mcp_client: MCP client for tool execution
        snapshot_s0: Snapshot of initial state (for validation)
        root_str: Root directory path
        init_plan: The init plan used to create S0 (will be re-executed)
    """
    import shutil as _shutil
    from pathlib import Path as _Path

    root_path = _Path(root_str)

    # Step 1: Wipe the workspace completely
    for item in root_path.iterdir():
        if item.is_dir():
            _shutil.rmtree(item)
        else:
            item.unlink()

    # Step 2: Re-execute init plan to restore S0 state
    if init_plan is not None:
        try:
            await _execute_init_plan(init_plan, mcp_client)
        except Exception as e:
            # Log but don't fail - caller may retry or handle differently
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to re-execute init plan during rollback: {e}")
    else:
        # Fallback: recreate directory structure from snapshot (files will be empty)
        if hasattr(snapshot_s0, "files"):
            for path, info in sorted(
                snapshot_s0.files.items(), key=lambda x: x[0].count("/")
            ):
                if info.is_directory and path != root_str:
                    try:
                        rel_path = _Path(path).relative_to(root_path)
                        target = root_path / rel_path
                        target.mkdir(parents=True, exist_ok=True)
                    except (ValueError, OSError):
                        pass


async def main(config_path: str = "configs/egts/config.yaml"):
    """Main pipeline execution (trajs2data mode only).

    Args:
        config_path: Path to configuration file
    """
    # Load configuration
    config = load_config(config_path)

    # Set up logging
    setup_logging(config)

    logger = logging.getLogger(__name__)
    logger.info("Starting MCP-Trajs2Data Pipeline")
    logger.info(f"Configuration loaded from {config_path}")

    # Initialize components
    maas_client = MaaSClient(config.maas)
    server_manager = MCPServerManager(config)

    world_envs = (
        getattr(config, "executable_world_envs", None)
        or getattr(config, "benchmark_envs", None)
        or []
    )
    env_pool = ExecutableWorldEnvPool(world_envs) if world_envs else None
    env_runner_cache = {}  # (worker_id, env_name) -> ComposeRunner

    try:
        # Get deduplication settings
        dedup_cfg = getattr(config.trajs2data, "deduplication", None)
        dedup_enabled = dedup_cfg.enabled if dedup_cfg else True
        max_trajs_per_problem = dedup_cfg.max_trajectories_per_problem if dedup_cfg else 3

        # Resolve configured servers
        all_servers = config.get_all_servers()
        task_config = config.trajs2data.task

        # Resolve required/primary servers from polymorphic task config
        required_servers = list(dict.fromkeys(getattr(task_config, "required_servers", [])))
        if not required_servers:
            logger.error(
                "Trajs2data task config must define at least one required MCP server"
            )
            return

        # Auto-inject benchmark_env when an env pool is configured
        if env_pool is not None and "benchmark_env" not in required_servers:
            required_servers.append("benchmark_env")

        primary_server = getattr(task_config, "primary_server", None) or required_servers[0]
        if primary_server not in required_servers:
            logger.error(
                f"Primary server '{primary_server}' is not in required_servers: {required_servers}"
            )
            return

        # Initialize Embedding Provider if semantic dedup or self-questioning is enabled
        embedding_provider = None
        semantic_deduplicator = None

        sq_cfg = getattr(config.trajs2data, "self_questioning", None)
        use_semantic_dedup = dedup_cfg and getattr(dedup_cfg, "use_semantic", False)
        use_sq_embeddings = sq_cfg and sq_cfg.enabled and sq_cfg.use_embeddings

        if use_semantic_dedup or use_sq_embeddings:
            try:
                # Use specific embedding config if available, else default MaaS
                emb_base_url = (
                    getattr(dedup_cfg, "embedding_base_url", None)
                    or config.maas.default.base_url
                )
                emb_api_key = (
                    getattr(dedup_cfg, "embedding_api_key", None)
                    or config.maas.default.api_key
                )
                emb_model = getattr(dedup_cfg, "embedding_model", "text-embedding-v4")

                logger.info(
                    f"Initializing Embedding Provider: {emb_model} @ {emb_base_url}"
                )
                embedding_provider = OpenAICompatibleEmbedding(
                    base_url=emb_base_url, api_key=emb_api_key, model=emb_model
                )

                if use_semantic_dedup:
                    vector_store_path = None
                    if getattr(dedup_cfg, "vector_store_path", None):
                        vector_store_path = Path(dedup_cfg.vector_store_path)

                    logger.info("Initializing Semantic Deduplicator...")
                    semantic_deduplicator = SemanticDeduplicator(
                        problem_similarity_threshold=dedup_cfg.problem_similarity_threshold,
                        trajectory_similarity_threshold=dedup_cfg.trajectory_similarity_threshold,
                        max_trajectories_per_problem=dedup_cfg.max_trajectories_per_problem,
                        embedding_provider=embedding_provider,
                        vector_store_path=vector_store_path,
                        use_chroma=True,
                    )
            except Exception as e:
                logger.error(f"Failed to initialize embedding components: {e}")
                logger.warning("Falling back to hash-based deduplication")

        storage = Storage(
            config.pipeline.output_dir,
            config.pipeline.exp_name,
            dedup_enabled=dedup_enabled,
            max_trajectories_per_problem=max_trajs_per_problem,
            semantic_deduplicator=semantic_deduplicator,
        )

        # Initialize Experience Manager if enabled (PRD 4.7)
        experience_manager = create_experience_manager(
            config=config.trajs2data,
            maas_client=maas_client,
            output_dir=storage.exp_dir,
            model_config=config.get_nl_rewrite_model_config(),
        )
        if experience_manager:
            logger.info(
                f"Experience Manager initialized: "
                f"{len(experience_manager.get_all_experiences())} experiences loaded"
            )
            # Persist an initialized store immediately so the file is always visible.
            experience_manager.save()

        # Determine start iteration for resume capability
        output_namespace = getattr(task_config, "output_namespace", None) or primary_server
        start_iteration = 0
        max_existing = storage.get_max_existing_iteration(
            primary_server, output_namespace=output_namespace
        )
        if max_existing >= 0:
            start_iteration = max_existing + 1
            logger.info(
                f"Found existing data up to iteration {max_existing}. Resuming from {start_iteration}."
            )
        else:
            logger.info("No existing data found. Starting from iteration 0.")

        logger.info(f"Initialized components")
        logger.info(f"Experiment Name: {storage.exp_name}")
        logger.info(f"Output Directory: {storage.exp_dir}")
        logger.info(
            f"MaaS Model for Trajectory Collection: {config.maas.models.trajectory_collection.model}"
        )
        logger.info(
            f"  Endpoint: {config.maas.models.trajectory_collection.base_url or config.maas.default.base_url}"
        )
        logger.info(f"STDIO MCP Servers: {list(config.stdio_mcp_servers.keys())}")
        logger.info(f"HTTP MCP Servers: {list(config.http_mcp_servers.keys())}")

        # Log trajs2data settings
        logger.info(f"Trajs2Data Pipeline Settings:")
        logger.info(f"  Total Episodes: {config.pipeline.num_iterations}")
        logger.info(f"  Start Iteration: {start_iteration}")

        task_config_obj = config.trajs2data.task
        logger.info(f"  Task type: {getattr(task_config_obj, 'task_type', 'unknown')}")
        logger.info(f"  Max steps (safety limit): {getattr(task_config_obj, 'max_steps', 'N/A')}")

        if isinstance(task_config_obj, FilesystemTaskConfig):
            fs_task = task_config_obj
            logger.info(
                f"  Filesystem n_tools: {fs_task.n_tools_min}-{fs_task.n_tools_max}"
            )
            logger.info(f"  Size profile: {fs_task.size_profile}")
            logger.info(f"  Init mode: {fs_task.init_mode}")
            if fs_task.init_mode in {"benchmark", "hybrid"}:
                logger.info(f"  Benchmark ratio: {fs_task.benchmark_ratio:.2f}")
                logger.info(f"  Benchmark source: {fs_task.benchmark_source}")
                logger.info(f"  Benchmark roots: {fs_task.benchmark_roots}")
                benchmark_cache_dir = (
                    Path(config.local.workspace_root) / fs_task.benchmark_cache_subdir
                )
                logger.info(f"  Benchmark cache dir: {benchmark_cache_dir}")
        else:
            # Generic task config — log available attributes
            for attr in ("n_tools_min", "n_tools_max", "prompt_domain", "output_namespace"):
                val = getattr(task_config_obj, attr, None)
                if val is not None:
                    logger.info(f"  {attr}: {val}")

        logger.info(f"  Max retry attempts: {config.trajs2data.max_attempts}")
        logger.info(
            f"  Synthesis in collection: {getattr(config.trajs2data, 'synthesis_in_collection', True)}"
        )
        logger.info(f"  NL rewrite model: {config.get_nl_rewrite_model_config().model}")
        logger.info(f"  Workspace Root: {config.local.workspace_root}")
        logger.info(f"  Number of Workers: {config.pipeline.num_workers}")

        # Log tool curriculum settings
        tool_curriculum = getattr(config.trajs2data, "tool_curriculum", None)
        if tool_curriculum:
            logger.info(f"Tool Curriculum Settings:")
            logger.info(f"  Base tools: {len(tool_curriculum.base_tools)} tools")
            logger.info(
                f"  Enabled stages: {[s.name for s in tool_curriculum.get_enabled_stages()]}"
            )
            logger.info(
                f"  Coverage min_success_per_tool: {tool_curriculum.coverage.min_success_per_tool}"
            )
            logger.info(
                "  Task type (mutation/retrieval) is determined automatically based on state diff"
            )

        # Log deduplication settings
        logger.info(f"Deduplication Settings:")
        logger.info(f"  Enabled: {dedup_enabled}")
        logger.info(f"  Max trajectories per problem: {max_trajs_per_problem}")

        dynamic_required_servers = {"benchmark_env"} if env_pool is not None else set()
        missing_servers = [
            s for s in required_servers if s not in all_servers and s not in dynamic_required_servers
        ]
        if missing_servers:
            logger.error(
                f"Trajs2data mode requires configured MCP servers: {required_servers}. "
                f"Missing: {missing_servers}"
            )
            return

        # Run one pipeline per primary task server; auxiliary required servers are started
        # inside each iteration by run_single_iteration_trajs2data(). Executable-world
        # pools inject `benchmark_env` dynamically at iteration time, so it may not
        # exist in the static server registry.
        if primary_server in all_servers:
            all_servers = {primary_server: all_servers[primary_server]}
        elif primary_server in dynamic_required_servers:
            all_servers = {primary_server: ("http", None)}
        else:
            logger.error(f"Primary server '{primary_server}' is not configured.")
            return

        for mcp_server_name in all_servers.keys():
            logger.info(f"\n{'#' * 60}")
            logger.info(f"Processing MCP Server: {mcp_server_name}")
            server_type, _ = all_servers[mcp_server_name]
            logger.info(f"Server Type: {server_type}")
            logger.info(f"{'#' * 60}\n")

            # Initialize coverage tracker beside flattened trajectory artifacts.
            coverage_namespace = getattr(task_config, "artifact_namespace", "")
            coverage_tracker = None
            coverage_tracker_cache: dict = {}  # {namespace -> CoverageTracker}
            if tool_curriculum:
                coverage_tracker = CoverageTracker(
                    output_dir=storage.exp_dir / coverage_namespace,
                    track_file=tool_curriculum.coverage.track_file,
                    min_success_per_tool=tool_curriculum.coverage.min_success_per_tool,
                )
                coverage_tracker_cache[coverage_namespace or "__root__"] = coverage_tracker
                logger.info(
                    f"Coverage tracker initialized: {coverage_tracker.coverage_path}"
                )

            # Initialize efficiency monitor if enabled (PRD 4.5)
            efficiency_monitor = None
            efficiency_cfg = getattr(config.trajs2data, "efficiency_monitor", None)
            if efficiency_cfg and efficiency_cfg.enabled:
                efficiency_monitor = EfficiencyMonitor(
                    min_success_rate=efficiency_cfg.min_success_rate,
                    window_size=efficiency_cfg.window_size,
                    auto_adjust=efficiency_cfg.auto_adjust,
                    reduce_target_n=efficiency_cfg.reduce_target_n_on_low_rate,
                    target_n_reduction_step=efficiency_cfg.target_n_reduction_step,
                    min_target_n=efficiency_cfg.min_target_n,
                )
                logger.info(
                    f"Efficiency monitor initialized: min_rate={efficiency_cfg.min_success_rate:.1%}, window={efficiency_cfg.window_size}"
                )

            # Initialize exploration recorder for anti-repetition prompting (PRD 4.1.2)
            # Note: Each iteration gets its own recorder (reset between episodes)
            # This tracks tool usage within a single episode to encourage diversity
            exploration_recorder = ExplorationStateRecorder(max_repetitions=2)
            logger.info(f"Exploration recorder initialized: max_repetitions=2")

            # Note: Sampler will be created per iteration (needs tools from MCP client)
            # We pass coverage_tracker so all iterations share the same state

            if config.pipeline.num_workers > 1:
                # Concurrent async execution with pre-started MCP servers
                num_workers = config.pipeline.num_workers
                world_run_id = storage.exp_name or "exp_default"
                logger.info(f"Using {num_workers} concurrent workers (pre-starting MCP servers)")

                # Resume logic: Start queue from start_iteration
                total_target = config.pipeline.num_iterations

                if start_iteration >= total_target:
                    logger.warning(
                        f"Target iterations ({total_target}) already reached (found {start_iteration} existing)."
                    )
                    logger.warning(
                        "If you want to generate more, please increase 'pipeline.num_iterations' in config.yaml."
                    )
                    return

                # Pre-start MCP servers for each worker (serialized once, then reused)
                task_config = config.trajs2data.task
                worker_required_servers = list(
                    dict.fromkeys(getattr(task_config, "required_servers", []))
                )
                worker_contexts = []  # List of (mcp_clients_dict, workspace_path)
                for wid in range(num_workers):
                    ws = Path(config.local.workspace_root) / f"worker_{wid}"
                    ws.mkdir(parents=True, exist_ok=True)
                    ws_str = str(ws.resolve())
                    clients = {}
                    for sname in worker_required_servers:
                        # Use negative IDs to avoid collision with iteration IDs
                        if sname in getattr(config, "http_mcp_servers", {}):
                            server_cfg = config.http_mcp_servers[sname]
                            clients[sname] = await server_manager.start_server(
                                sname,
                                -(wid + 1),
                                workspace_path=ws_str,
                                url=server_cfg.url,
                                headers=build_world_session_headers(
                                    getattr(server_cfg, "headers", {}) or {},
                                    run_id=world_run_id,
                                    worker_id=wid,
                                ),
                            )
                        else:
                            clients[sname] = await server_manager.start_server(
                                sname, -(wid + 1), workspace_path=ws_str
                            )
                    worker_contexts.append((clients, ws))
                    logger.info(f"Worker {wid}: MCP servers pre-started (workspace={ws})")

                # Create task queue
                task_queue = asyncio.Queue()
                for i in range(start_iteration, total_target):
                    await task_queue.put(i)
                _SENTINEL = None
                for _ in range(num_workers):
                    await task_queue.put(_SENTINEL)

                # Worker coroutine — reuses pre-started servers
                async def worker(worker_id, pre_clients, workspace):
                    """Process tasks from the queue using pre-started MCP servers."""
                    results = []
                    while True:
                        iteration = await task_queue.get()
                        if iteration is None:
                            task_queue.task_done()
                            break

                        selected_env = None
                        iteration_pre_clients = dict(pre_clients)
                        iteration_dynamic_clients = {}
                        if env_pool is not None:
                            selected_env = env_pool.select(iteration=iteration, worker_id=worker_id).env
                            runner_key = (worker_id, selected_env.name)
                            runner = env_runner_cache.get(runner_key)
                            if runner is None:
                                runner = ComposeRunner(spec=selected_env, worker_id=worker_id)
                                env_runner_cache[runner_key] = runner

                            await runner.ensure_started()
                            await runner.wait_healthy()
                            await runner.reset()

                            iteration_dynamic_clients[
                                "benchmark_env"
                            ] = await server_manager.start_http_client(
                                server_name="benchmark_env",
                                url=selected_env.http_mcp_url,
                                headers=build_world_session_headers(
                                    selected_env.http_mcp_headers,
                                    run_id=world_run_id,
                                    worker_id=worker_id,
                                ),
                                timeout=getattr(selected_env, "http_timeout_s", 30),
                                iteration=iteration,
                            )
                            iteration_pre_clients["benchmark_env"] = (
                                iteration_dynamic_clients["benchmark_env"]
                            )

                        logger.info(
                            f"Worker {worker_id}: Processing iteration {iteration + 1}/{total_target}"
                            + (f" (env={selected_env.name})" if selected_env is not None else "")
                        )
                        try:
                            iteration_recorder = ExplorationStateRecorder(max_repetitions=2)
                            result = await run_single_iteration_trajs2data(
                                mcp_server_name,
                                config,
                                maas_client,
                                storage,
                                iteration,
                                server_manager,
                                sampler=None,
                                coverage_tracker=coverage_tracker,
                                efficiency_monitor=efficiency_monitor,
                                exploration_recorder=iteration_recorder,
                                embedding_provider=embedding_provider,
                                experience_manager=experience_manager,
                                pre_started_clients=iteration_pre_clients,
                                reuse_workspace=workspace,
                                coverage_tracker_cache=coverage_tracker_cache,
                                selected_env=selected_env,
                            )
                            results.append(result)
                        except Exception as e:
                            logger.error(
                                f"Worker {worker_id}: Unhandled exception in iteration {iteration}: {e}",
                                exc_info=True,
                            )
                            results.append(False)
                        finally:
                            for sname, client in iteration_dynamic_clients.items():
                                try:
                                    await _cleanup_world_session(client, sname, logger)
                                    await client.disconnect()
                                except BaseException as e:
                                    if not isinstance(e, Exception):
                                        logger.debug(
                                            f"Worker {worker_id}: Non-fatal cleanup signal "
                                            f"for iteration {iteration} server {sname}: {e}"
                                        )
                                    else:
                                        logger.warning(
                                            f"Worker {worker_id}: Failed to cleanup iteration "
                                            f"{iteration} server {sname}: {e}"
                                        )
                                finally:
                                    server_manager.unregister_server(sname, iteration)

                        try:
                            storage.save_statistics()
                        except Exception as e:
                            logger.warning(f"Worker {worker_id}: Failed to save statistics: {e}")

                        task_queue.task_done()
                    return results

                # Launch workers
                workers = []
                for i in range(num_workers):
                    clients_i, ws_i = worker_contexts[i]
                    workers.append(asyncio.create_task(worker(i, clients_i, ws_i)))

                # Wait for all workers to complete
                all_results = await asyncio.gather(*workers, return_exceptions=True)

                # Cleanup pre-started servers
                for wid, (clients, ws) in enumerate(worker_contexts):
                    for sname, client in clients.items():
                        try:
                            await _cleanup_world_session(client, sname, logger)
                            await client.disconnect()
                        except BaseException as e:
                            if isinstance(e, Exception):
                                logger.warning(f"Failed to cleanup worker {wid} server {sname}: {e}")
                            else:
                                logger.debug(f"Non-fatal cleanup signal for worker {wid} server {sname}: {e}")
                        finally:
                            server_manager.unregister_server(sname, -(wid + 1))

                # Flatten results
                total_results = []
                for r in all_results:
                    if isinstance(r, Exception):
                        logger.error(f"Worker crashed with: {r}")
                    elif isinstance(r, list):
                        total_results.extend(r)

                logger.info(
                    f"\nCompleted {len(total_results)} new iterations (resumed from {start_iteration}) with {num_workers} workers"
                )

            else:
                # Single-threaded execution
                logger.info(f"Using single-threaded execution")
                world_run_id = storage.exp_name or "exp_default"

                # Resume logic for single-threaded
                total_target = config.pipeline.num_iterations
                if start_iteration >= total_target:
                    logger.warning(
                        f"Target iterations ({total_target}) already reached (found {start_iteration} existing)."
                    )
                    return

                for i in range(start_iteration, total_target):
                    logger.info(f"Iteration {i + 1}/{config.pipeline.num_iterations}")

                    selected_env = None
                    single_pre_clients = {}
                    single_dynamic_clients = {}
                    if env_pool is not None:
                        selected_env = env_pool.select(iteration=i, worker_id=0).env
                        runner_key = (0, selected_env.name)
                        runner = env_runner_cache.get(runner_key)
                        if runner is None:
                            runner = ComposeRunner(spec=selected_env, worker_id=0)
                            env_runner_cache[runner_key] = runner

                        await runner.ensure_started()
                        await runner.wait_healthy()
                        await runner.reset()

                        single_dynamic_clients[
                            "benchmark_env"
                        ] = await server_manager.start_http_client(
                            server_name="benchmark_env",
                            url=selected_env.http_mcp_url,
                            headers=build_world_session_headers(
                                selected_env.http_mcp_headers,
                                run_id=world_run_id,
                                worker_id=0,
                            ),
                            timeout=getattr(selected_env, "http_timeout_s", 30),
                            iteration=i,
                        )
                        single_pre_clients["benchmark_env"] = single_dynamic_clients[
                            "benchmark_env"
                        ]

                    try:
                        await run_single_iteration_trajs2data(
                            mcp_server_name,
                            config,
                            maas_client,
                            storage,
                            i,
                            server_manager,  # NEW: Pass server manager
                            sampler=None,  # Created per iteration
                            coverage_tracker=coverage_tracker,
                            efficiency_monitor=efficiency_monitor,
                            exploration_recorder=exploration_recorder,
                            embedding_provider=embedding_provider,
                            experience_manager=experience_manager,
                            pre_started_clients=single_pre_clients or None,
                            coverage_tracker_cache=coverage_tracker_cache,
                            selected_env=selected_env,
                        )
                    finally:
                        for sname, client in single_dynamic_clients.items():
                            try:
                                await _cleanup_world_session(client, sname, logger)
                                await client.disconnect()
                            except Exception as e:
                                logger.warning(
                                    f"Failed to cleanup iteration {i} server {sname}: {e}"
                                )
                            finally:
                                server_manager.unregister_server(sname, i)

                    # Reset exploration recorder between episodes
                    exploration_recorder.reset()

                    # Save statistics after each iteration
                    storage.save_statistics()

            # Log efficiency monitor summary if enabled
            if efficiency_monitor is not None:
                summary = efficiency_monitor.get_summary()
                logger.info(f"\nEfficiency Monitor Summary:")
                logger.info(f"  Total attempted: {summary['total_attempted']}")
                logger.info(f"  Total saved: {summary['total_saved']}")
                logger.info(f"  Total filtered: {summary['total_filtered']}")
                logger.info(f"  Total deduped: {summary['total_deduped']}")
                logger.info(
                    f"  Overall success rate: {summary['overall_success_rate']:.1%}"
                )
                logger.info(f"  Window success rate: {summary['window_success_rate']:.1%}")
                if summary["current_adjustment"] is not None:
                    logger.info(
                        f"  Current target_n adjustment: {summary['current_adjustment']}"
                    )

            # Save final coverage data
            if coverage_tracker:
                coverage_tracker.save()
                coverage_report = coverage_tracker.get_detailed_report()
                coverage_summary = coverage_report["summary"]
                logger.info(f"\nCoverage Report for {mcp_server_name}:")
                logger.info(f"  Total tools: {coverage_summary['total_tools']}")
                logger.info(
                    "  Tools observed successfully: "
                    f"{coverage_summary.get('observed_successful_tools', 0)}"
                )
                logger.info(
                    "  Covered tools "
                    f"(>= {coverage_summary.get('min_success_per_tool', 0)} successes): "
                    f"{coverage_summary['covered_tools']}"
                )
                logger.info(
                    f"  Coverage rate: {coverage_summary['coverage_rate']:.2%}"
                )
                logger.info(
                    f"  Uncovered: {coverage_report['uncovered'][:5]}..."
                    if len(coverage_report["uncovered"]) > 5
                    else f"  Uncovered: {coverage_report['uncovered']}"
                )

            # Save all per-namespace coverage trackers (multi-domain worlds)
            if coverage_tracker_cache:
                for ns, tracker in coverage_tracker_cache.items():
                    if tracker is not coverage_tracker:  # avoid double-save
                        tracker.save()
                        ns_report = tracker.get_detailed_report()
                        logger.info(
                            f"\nCoverage Report for namespace '{ns}': "
                            f"{ns_report['summary']['covered_tools']}/{ns_report['summary']['total_tools']} "
                            f"({ns_report['summary']['coverage_rate']:.2%})"
                        )

        # Final statistics
        logger.info("\n" + "=" * 60)
        logger.info("Pipeline Complete!")
        logger.info("=" * 60)

        stats = storage.get_statistics()
        synthesis_in_collection = bool(
            getattr(config.trajs2data, "synthesis_in_collection", True)
        )

        if synthesis_in_collection:
            logger.info("[EGTS Synthesis-in-Collection Mode]")
        else:
            logger.info("[EGTS Collection Mode]")
        logger.info(f"Total Episodes Attempted: {stats['trajs2data_total']}")
        logger.info(f"Raw Episodes Saved: {stats.get('trajs2data_raw', 0)}")
        logger.info(f"Synthesized Trajectories Saved: {stats['trajs2data_valid']}")
        logger.info(f"Filtered Out: {stats['trajs2data_filtered']}")
        logger.info(f"Deduplicated: {stats.get('trajs2data_deduplicated', 0)}")
        logger.info(f"Salvaged: {stats.get('trajs2data_salvaged', 0)}")
        logger.info(f"Unique Problems: {stats.get('unique_problems', 'N/A')}")
        logger.info(f"Saved Outputs: {stats.get('trajs2data_saved', 0)}")
        logger.info(f"Collection Save Rate: {stats['trajs2data_success_rate']:.2%}")
        if synthesis_in_collection:
            logger.info(
                f"Valid Synthesis Rate: {stats.get('trajs2data_valid_success_rate', 0.0):.2%}"
            )
        else:
            logger.info("Synthesis in collection: disabled")
        logger.info(f"Salvage Rate: {stats.get('salvage_rate', 0.0):.2%}")

        # Failure statistics
        avg_failures = stats.get("avg_failures_per_episode", 0.0)
        total_failures = stats.get("total_tool_failures", 0)
        if total_failures > 0:
            logger.info(f"\n[Failure Analysis]")
            logger.info(f"Total Tool Failures: {total_failures}")
            logger.info(f"Avg Failures per Episode: {avg_failures:.2f}")

            # Top failing tools
            failure_by_tool = stats.get("failure_by_tool", {})
            if failure_by_tool:
                top_failures = sorted(
                    failure_by_tool.items(), key=lambda x: x[1], reverse=True
                )[:5]
                logger.info(f"Top Failing Tools: {top_failures}")

        # Dual-mode stats
        mutation_count = stats.get("trajs2data_mutation", 0)
        retrieval_count = stats.get("trajs2data_retrieval", 0)
        if mutation_count or retrieval_count:
            logger.info(f"\n[Task Type Distribution]")
            logger.info(f"Mutation Episodes: {mutation_count}")
            logger.info(f"Retrieval Episodes: {retrieval_count}")

        # Deduplication stats
        dedup_stats = storage.get_dedup_stats()
        if dedup_stats["enabled"]:
            logger.info(f"\n[Deduplication Statistics]")
            logger.info(f"Deduplicated: {dedup_stats['deduplicated_count']}")
            logger.info(f"Dedup Rate: {dedup_stats['dedup_rate']:.1%}")
            logger.info(f"Unique Problems: {dedup_stats['unique_problems']}")
            logger.info(
                f"Avg Trajectories per Problem: {dedup_stats['trajectories_per_problem']['avg']:.1f}"
            )
            logger.info(
                f"Problems at Capacity ({dedup_stats['max_trajectories_per_problem']}): {dedup_stats['problems_at_capacity']}"
            )

        # Save comprehensive quality report only when collection also performs
        # synthesis. Raw-only exploration is judged by save/coverage/source stats;
        # quality/yield is computed by the offline data_synthesis stage.
        if synthesis_in_collection:
            logger.info(f"\n[Saving Quality Report]")
            quality_report = storage.save_quality_report()
            logger.info(f"Yield Rate: {quality_report['summary']['yield_rate']:.2%}")
        else:
            logger.info(
                "\n[Quality Report] Skipped in collection-only mode; "
                "run data_synthesis to compute synthesis yield/quality."
            )

        logger.info(f"\nResults saved to: {config.pipeline.output_dir}")

        # Ensure background experience extractions complete and the store is
        # persisted before the process exits.
        if experience_manager is not None:
            try:
                waited = await experience_manager.flush()
                if waited > 0:
                    logger.info(
                        "Experience store flushed (%d background task(s) awaited).",
                        waited,
                    )
            except Exception as e:
                logger.warning("Experience manager flush failed: %s", e)
    finally:
        for (worker_id, env_name), runner in list(env_runner_cache.items()):
            try:
                await runner.stop()
            except Exception as e:
                logger.warning(
                    f"Failed to stop executable world runner {env_name} for worker {worker_id}: {e}"
                )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP-Trajs2Data Pipeline")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/egts/config.yaml",
        help="Path to configuration file (default: configs/egts/config.yaml)",
    )

    args = parser.parse_args()
    asyncio.run(main(config_path=args.config))
