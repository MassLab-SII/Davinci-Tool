"""
Standalone replay synthesis from existing raw exploration trajectories.

Usage:
    PYTHONPATH=src/egts python src/egts/data_collection/replay_from_raw.py \\
        --input output/exploration_worlds/deepseekv4/exp_tool_sandbox \\
        --config configs/egts/tool_sandbox.yaml \\
        --output output/replay_synthesis_prod \\
        [--limit 100] [--dry-run]

The MCP server for the target world must already be running (managed by the
calling shell script or started via --start-server).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from data_collection.utils.config import load_config
from data_collection.mcp_servers.http_server import MCPHttpServer
from data_collection.replay_synthesis import (
    ReplaySynthesisConfig,
    ReplaySynthesisRunner,
    _safe_json_dumps,
    build_replay_review_record,
    save_replay_artifacts,
)
from data_collection.utils.storage import _atomic_write_json

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.warning("Failed to load %s", path, exc_info=True)
        return None


# ── checkpoint / resume ────────────────────────────────────────────────


def _load_checkpoint(output_dir: Path) -> Dict[str, Any]:
    """Load the checkpoint tracking which source episodes have been processed."""
    cp_path = output_dir / "trajs2data_replay_synthesis" / "checkpoint.json"
    if cp_path.exists():
        try:
            return json.loads(cp_path.read_text("utf-8"))
        except Exception:
            logger.warning("Corrupt checkpoint file, starting fresh", exc_info=True)
    return {"processed": {}, "resumed_count": 0}


def _save_checkpoint(
    output_dir: Path,
    checkpoint: Dict[str, Any],
    source_ep: str,
    status: str,
    replay_dir: str = "",
    error: str = "",
    quality_tier: str = "",
    quality_score: float = 0.0,
) -> None:
    """Record a processed source episode in the checkpoint."""
    entry: Dict[str, Any] = {
        "status": status,        # "accepted" | "rejected" | "error"
        "replay_dir": replay_dir,
    }
    if error:
        entry["error"] = error
    if quality_tier:
        entry["quality_tier"] = quality_tier
    if quality_score:
        entry["quality_score"] = quality_score
    checkpoint["processed"][source_ep] = entry
    cp_path = output_dir / "trajs2data_replay_synthesis" / "checkpoint.json"
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(cp_path, checkpoint)


def _discover_raw_episodes(input_dir: Path) -> List[Path]:
    """Find all raw episode directories under input_dir.

    Expects the standard layout:
        input_dir/
          trajs2data_raw/
            trajs2data_000000/
              trajectory.json  raw_context.json  metadata.json
            trajs2data_000001/
              ...
    """
    raw_dir = input_dir / "trajs2data_raw"
    if not raw_dir.is_dir():
        # Maybe input_dir IS a raw episode directory
        if (input_dir / "trajectory.json").is_file():
            return [input_dir]
        logger.warning("No trajs2data_raw/ found in %s", input_dir)
        return []

    episodes: List[Path] = []
    for ep in sorted(raw_dir.iterdir()):
        if ep.is_dir() and (ep / "trajectory.json").is_file():
            episodes.append(ep)
    return episodes


def _update_replay_registry(
    *,
    registry_dir: Path,
    episode_name: str,
    quality_tier: str,
    quality_score: float,
    accepted: bool,
    task_type: str,
    num_steps: int,
    problem_spec: Any,
    min_quality_tier: str = "acceptable",
    source_episode: str = "",
) -> None:
    """Real-time append to replay registry, gated by quality tier.

    Only episodes meeting *min_quality_tier* are added to the registry entries.
    The registry is atomically rewritten after each episode.
    """
    registry_path = registry_dir / "registry.json"
    registry_dir.mkdir(parents=True, exist_ok=True)

    try:
        if registry_path.exists():
            registry = json.loads(registry_path.read_text("utf-8"))
        else:
            registry = {
                "created_at": datetime.now().isoformat(),
                "min_quality_tier": min_quality_tier,
                "total_episodes": 0,
                "registry_entries": [],
                "quality_distribution": {"high_quality": 0, "acceptable": 0, "reject": 0},
            }
    except Exception:
        registry = {
            "created_at": datetime.now().isoformat(),
            "min_quality_tier": min_quality_tier,
            "total_episodes": 0,
            "registry_entries": [],
            "quality_distribution": {"high_quality": 0, "acceptable": 0, "reject": 0},
        }

    registry["total_episodes"] += 1
    if quality_tier in registry["quality_distribution"]:
        registry["quality_distribution"][quality_tier] += 1

    tier_rank = {"high_quality": 2, "acceptable": 1, "reject": 0}
    if tier_rank.get(quality_tier, -1) >= tier_rank.get(min_quality_tier, 1):
        problem_text = ""
        try:
            if problem_spec is not None:
                pd = problem_spec.__dict__ if hasattr(problem_spec, "__dict__") else {}
                problem_text = str(pd.get("problem", "") or "")
        except Exception:
            pass

        entry = {
            "episode_dir": episode_name,
            "source_episode": source_episode,
            "quality_tier": quality_tier,
            "quality_score": quality_score,
            "accepted": accepted,
            "task_type": str(task_type or ""),
            "num_steps": num_steps,
            "timestamp": datetime.now().isoformat(),
            "problem": problem_text[:200],
        }
        registry["registry_entries"].append(entry)

    registry["updated_at"] = datetime.now().isoformat()
    _atomic_write_json(registry_path, registry)


def _append_review_to_jsonl(
    *,
    data_dir: Path,
    review_record: Dict[str, Any],
) -> None:
    """Append a validated review record to the aggregated replay_data.jsonl.

    One JSON object per line — crash-safe, truly appendable, and trivial for
    downstream training pipelines to consume (json.loads per line).
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = data_dir / "replay_data.jsonl"
    try:
        line = _safe_json_dumps(review_record, ensure_ascii=False)
        with open(jsonl_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        logger.exception("Failed to append review record to %s", jsonl_path)


def _resolve_model_config(config: Any, model_role: str) -> Optional[Any]:
    """Resolve a model config by role name from the global config."""
    try:
        models = config.maas.models
        if model_role == "nl_rewrite":
            return models.nl_rewrite
        if model_role == "judge" or model_role == "judge_model":
            return models.judge
        return models.trajectory_collection
    except Exception:
        return None


def _build_maas_client(config: Any) -> Any:
    """Create a MaaS client from config."""
    try:
        from data_collection.maas_client import MaaSClient

        return MaaSClient(config.maas)
    except Exception:
        logger.warning("Could not create MaaS client — LLM features disabled")
        return None


# ── MCP helpers ──────────────────────────────────────────────────────


async def _connect_mcp_client(config: Any, server_name: str) -> Any:
    """Connect to a running HTTP MCP server."""
    http_servers = getattr(config, "http_mcp_servers", {})
    server_cfg = http_servers.get(server_name)
    if server_cfg is None:
        raise RuntimeError(
            f"Server '{server_name}' not found in config.http_mcp_servers"
        )
    url = server_cfg.url
    headers = dict(getattr(server_cfg, "headers", {}) or {})
    timeout = getattr(server_cfg, "timeout", 60)

    # Build a stable world-session id so the executable world can bind
    # per-episode runtimes to this replay session.
    from data_collection.executable_worlds.session_headers import (
        build_world_session_id,
        WORLD_SESSION_HEADER,
    )
    run_id = f"replay_{int(time.time())}"
    headers.setdefault(WORLD_SESSION_HEADER, build_world_session_id(run_id, worker_id=0))

    client = MCPHttpServer(url=url, headers=headers, timeout=timeout)
    await client.start()
    logger.info("Connected to MCP server %s at %s", server_name, url)
    return client


async def _fetch_tool_schemas(mcp_client: Any) -> List[Dict[str, Any]]:
    """Fetch tool schemas from a connected MCP client."""
    try:
        resp = await mcp_client.list_tools()
        if isinstance(resp, dict):
            return resp.get("tools", [])
        return list(resp) if resp else []
    except Exception:
        logger.warning("Could not fetch tool schemas", exc_info=True)
        return []


# ── main entry ───────────────────────────────────────────────────────


async def run_replay_on_raw_episodes(
    *,
    input_dir: Path,
    config: Any,
    output_dir: Path,
    limit: int = 0,
    dry_run: bool = False,
    resume: bool = True,
) -> Dict[str, Any]:
    """Run replay synthesis on all raw episodes in input_dir.

    With *resume=True* (default), episodes already processed and accepted in a
    previous run are skipped.  The checkpoint lives at
    ``<output_dir>/trajs2data_replay_synthesis/checkpoint.json``.
    Pass ``--no-resume`` to force re-processing everything.

    Returns a summary dict with counts and per-episode stats.
    """
    # ── Resolve config ──
    trajs2data_cfg = getattr(config, "trajs2data", None)
    if trajs2data_cfg is None:
        raise RuntimeError("Config has no 'trajs2data' section")

    replay_cfg_pydantic = getattr(trajs2data_cfg, "replay_synthesis", None)
    if replay_cfg_pydantic is None:
        raise RuntimeError("Config has no 'trajs2data.replay_synthesis' section")

    # Build the plain dataclass ReplaySynthesisConfig from pydantic fields
    runner_cfg = ReplaySynthesisConfig(
        enabled=True,
        max_problem_candidates=getattr(replay_cfg_pydantic, "max_problem_candidates", 3),
        max_replay_attempts=getattr(replay_cfg_pydantic, "max_replay_attempts", 2),
        min_quality_tier=getattr(replay_cfg_pydantic, "min_quality_tier", "acceptable"),
        tool_sequence_selection=getattr(replay_cfg_pydantic, "tool_sequence_selection", "heuristic"),
        verify_final_state=getattr(replay_cfg_pydantic, "verify_final_state", True),
        save_failed_replays=getattr(replay_cfg_pydantic, "save_failed_replays", True),
        harness_mode=getattr(replay_cfg_pydantic, "harness_mode", "full"),
        harness_max_retries_per_step=getattr(replay_cfg_pydantic, "harness_max_retries_per_step", 2),
        harness_model=getattr(replay_cfg_pydantic, "harness_model", "trajectory_collection"),
        harness_fallback_threshold=getattr(replay_cfg_pydantic, "harness_fallback_threshold", 0.5),
        preserve_failure_recovery_chains=getattr(replay_cfg_pydantic, "preserve_failure_recovery_chains", True),
        dependency_relevance_filter=getattr(replay_cfg_pydantic, "dependency_relevance_filter", True),
        llm_problem_synthesis=getattr(replay_cfg_pydantic, "llm_problem_synthesis", True),
        max_dependency_distance=getattr(replay_cfg_pydantic, "max_dependency_distance", 5),
        polish_enabled=getattr(replay_cfg_pydantic, "polish_enabled", True),
        polish_model=getattr(replay_cfg_pydantic, "polish_model", "judge_model"),
        enable_quality_judge=getattr(replay_cfg_pydantic, "enable_quality_judge", True),
        judge_hard_weight=getattr(replay_cfg_pydantic, "judge_hard_weight", 0.70),
        judge_soft_weight=getattr(replay_cfg_pydantic, "judge_soft_weight", 0.20),
        judge_dual_bonus=getattr(replay_cfg_pydantic, "judge_dual_bonus", 0.10),
        judge_threshold_high=getattr(replay_cfg_pydantic, "judge_threshold_high", 0.85),
        judge_threshold_acceptable=getattr(replay_cfg_pydantic, "judge_threshold_acceptable", 0.70),
        min_original_tool_calls=getattr(replay_cfg_pydantic, "min_original_tool_calls", 3),
        min_selected_tool_calls=getattr(replay_cfg_pydantic, "min_selected_tool_calls", 2),
        tool_name_noise_extra=getattr(replay_cfg_pydantic, "tool_name_noise_extra", None),
        tool_name_noise_exclude=getattr(replay_cfg_pydantic, "tool_name_noise_exclude", None),
    )

    # ── Connect to MCP server ──
    task_cfg = trajs2data_cfg.task
    primary_server = getattr(task_cfg, "primary_server", None)
    required_servers = getattr(task_cfg, "required_servers", [])
    read_only_tools: Optional[List[str]] = getattr(task_cfg, "read_only_tools", None)
    if not primary_server and required_servers:
        primary_server = required_servers[0]
    if not primary_server:
        raise RuntimeError("No primary_server found in task config")

    logger.info("Connecting to MCP server: %s", primary_server)
    mcp_client = await _connect_mcp_client(config, primary_server)
    tools = await _fetch_tool_schemas(mcp_client)

    # ── Resolve model config ──
    maas_client = _build_maas_client(config)

    problem_synthesis_model_config = None
    if runner_cfg.llm_problem_synthesis:
        problem_synthesis_model_config = _resolve_model_config(config, "nl_rewrite")

    harness_model_config = None
    if runner_cfg.harness_mode != "disabled":
        harness_model_config = _resolve_model_config(config, runner_cfg.harness_model)

    polish_model_config = None
    if runner_cfg.polish_enabled:
        role = runner_cfg.polish_model  # "judge_model" or "nl_rewrite"
        if role == "nl_rewrite":
            polish_model_config = _resolve_model_config(config, "nl_rewrite")
        else:
            polish_model_config = _resolve_model_config(config, "judge")

    judge_model_config = None
    if runner_cfg.enable_quality_judge:
        judge_model_config = _resolve_model_config(config, "judge")

    # ── Discover episodes ──
    episodes = _discover_raw_episodes(input_dir)
    if limit > 0:
        episodes = episodes[:limit]
    logger.info("Found %d raw episodes in %s", len(episodes), input_dir)

    # ── Build world context ──
    world_ctx: Dict[str, Any] = {}
    try:
        server_metadata = getattr(config.http_mcp_servers, primary_server, None)
        if server_metadata:
            metadata = getattr(server_metadata, "metadata", {}) or {}
            prompt_domain = metadata.get("prompt_domain", "")
            output_ns = metadata.get("output_namespace", "")
            world_ctx = {
                "engine": "EGTS",
                "domain": f"{prompt_domain} executable world",
                "operator_role": "virtual assistant agent",
                "output_namespace": output_ns,
            }
    except Exception:
        pass

    # ── Resume checkpoint ──
    checkpoint: Dict[str, Any] = {"processed": {}, "resumed_count": 0}
    if resume:
        checkpoint = _load_checkpoint(output_dir)
    stats = {
        "total": len(episodes),
        "accepted": 0,
        "rejected": 0,
        "errored": 0,
        "skipped": 0,
        "quality_distribution": {"high_quality": 0, "acceptable": 0, "reject": 0},
        "per_episode": [],
    }

    # ── Process episodes ──
    runner = ReplaySynthesisRunner(runner_cfg)

    for idx, ep_dir in enumerate(episodes):
        ep_name = ep_dir.name

        # ── Resume: skip already-accepted source episodes ──
        if resume and ep_name in checkpoint.get("processed", {}):
            prev = checkpoint["processed"][ep_name]
            if prev.get("status") == "accepted":
                replay_dir_name = prev.get("replay_dir", "")
                replay_path = output_dir / "trajs2data_replay_synthesis" / replay_dir_name
                if replay_dir_name and replay_path.is_dir():
                    logger.info(
                        "── [%d/%d] %s — SKIP (already accepted in %s)",
                        idx + 1, len(episodes), ep_name, replay_dir_name,
                    )
                    stats["skipped"] += 1
                    stats["accepted"] += 1
                    prev_tier = prev.get("quality_tier", "high_quality")
                    if prev_tier in stats["quality_distribution"]:
                        stats["quality_distribution"][prev_tier] += 1
                    stats["per_episode"].append({
                        "episode": ep_name,
                        "resumed": True,
                        "replay_dir": replay_dir_name,
                        "quality_tier": prev_tier,
                    })
                    continue
                else:
                    logger.info(
                        "── [%d/%d] %s — RE-RUN (previous replay %s missing)",
                        idx + 1, len(episodes), ep_name, replay_dir_name,
                    )

        try:
            traj_dict = _load_json(ep_dir / "trajectory.json")
            raw_ctx = _load_json(ep_dir / "raw_context.json")
            if traj_dict is None:
                logger.warning("Skipping %s: no trajectory.json", ep_name)
                stats["errored"] += 1
                continue

            # Build a lightweight object the runner can call getattr on
            traj_obj = SimpleNamespace(
                tool_calls=traj_dict.get("tool_calls", []),
                messages=traj_dict.get("messages", []),
                to_dict=lambda: traj_dict,
            )

            state_evidence = (raw_ctx or {}).get("state_evidence")
            retrieval_spec = (raw_ctx or {}).get("retrieval_spec")
            task_type = (raw_ctx or {}).get("task_type", "retrieval")
            language = (raw_ctx or {}).get("language", "en")

            # ── Pre-filter: skip episodes with too few original tool calls ──
            original_call_count = len(traj_obj.tool_calls)
            min_orig = getattr(runner_cfg, "min_original_tool_calls", 3)
            if original_call_count < min_orig:
                logger.info(
                    "  SKIP   %s  reason=too_few_original_calls  original=%d < min=%d",
                    ep_name, original_call_count, min_orig,
                )
                stats["skipped"] += 1
                stats["per_episode"].append({
                    "episode": ep_name,
                    "accepted": False,
                    "rejected_reason": "pre_filter_too_few_original_calls",
                    "quality_tier": "reject",
                    "quality_score": 0.0,
                    "tool_steps": original_call_count,
                })
                # Mark as processed in checkpoint so resume doesn't re-try
                _save_checkpoint(
                    output_dir, checkpoint, source_ep=ep_name,
                    status="skipped_pre_filter",
                    replay_dir="",
                    quality_tier="reject",
                    quality_score=0.0,
                )
                continue

            # ── Restore world session for this episode ──
            # Always call /admin/reset to bind a fresh episode runtime.
            # Pass task_key / task_id when available for deterministic
            # replay, otherwise let the world pick via random seed.
            wctx = (raw_ctx or {}).get("world_context") or {}
            reset_meta = (wctx.get("reset") or {}).get("metadata") or {}
            episode_reset_meta = reset_meta.get("episode_reset_meta") or {}
            task_key = episode_reset_meta.get("task_key")
            task_id = episode_reset_meta.get("task_id")
            if hasattr(mcp_client, "admin_request"):
                reset_body: Dict[str, Any] = {"seed": idx}
                if task_key:
                    reset_body["task_key"] = task_key
                if task_id:
                    reset_body["task_id"] = task_id
                try:
                    _reset_resp = await mcp_client.admin_request(
                        "/admin/reset", method="POST", body=reset_body
                    )
                    logger.info(
                        "  🌍 Episode reset: domain=%s task=%s",
                        _reset_resp.get("selected_domain", "?") or _reset_resp.get("world", "?"),
                        _reset_resp.get("task_key") or _reset_resp.get("task_id", "?"),
                    )
                except Exception as e:
                    logger.error(
                        "  Admin reset failed for episode %s: %s — skipping episode",
                        ep_name, e,
                    )
                    stats["errored"] += 1
                    stats["per_episode"].append({
                        "episode": ep_name,
                        "accepted": False,
                        "rejected_reason": "admin_reset_failed",
                        "traceback": traceback.format_exc()[:500],
                    })
                    _save_checkpoint(
                        output_dir, checkpoint, source_ep=ep_name,
                        status="error",
                        error=f"admin_reset_failed: {e}",
                    )
                    continue

            ep_output_dir = output_dir / "trajs2data_replay_synthesis"
            if dry_run:
                logger.info("  [dry-run] Would save to %s", ep_output_dir)
                continue

            ep_output_dir.mkdir(parents=True, exist_ok=True)

            result = await runner.run(
                trajectory=traj_obj,
                task_type=task_type,
                state_evidence=state_evidence,
                retrieval_spec=retrieval_spec,
                mcp_client=mcp_client,
                tools=tools,
                original_s1=None,
                artifact_dir=ep_output_dir,
                language=language,
                maas_client=maas_client,
                model_config=problem_synthesis_model_config,
                harness_model_config=harness_model_config,
                polish_model_config=polish_model_config,
                judge_model_config=judge_model_config,
                world_context=world_ctx,
                read_only_tools=read_only_tools,
            )

            # save_replay_artifacts creates its own subdirectory (e.g. replay_<ts>_<uuid>)
            saved_dir_name = Path(result.artifact_dir).name if result.artifact_dir else f"replay_{idx:06d}"

            review = result.review_record or {}
            selected_steps = len(result.selection.selected_calls) if result.selection else 0
            ep_stat = {
                "episode": ep_name,
                "accepted": result.accepted,
                "rejected_reason": result.rejected_reason,
                "quality_tier": review.get("quality_tier", "reject"),
                "quality_score": review.get("quality_score", 0.0),
                "hard_judge_pass": review.get("hard_judge_pass"),
                "soft_judge_pass": review.get("soft_judge_pass"),
                "tool_steps": selected_steps,
            }

            # ── Post-filter: skip episodes where tool selection collapsed below threshold ──
            min_selected = getattr(runner_cfg, "min_selected_tool_calls", 2)
            if selected_steps < min_selected:
                logger.info(
                    "  SKIP   %s  reason=too_few_selected_calls  selected=%d < min=%d  original=%d",
                    ep_name, selected_steps, min_selected, original_call_count,
                )
                # Override the stat to reflect pre-filter rejection
                ep_stat["accepted"] = False
                ep_stat["rejected_reason"] = "post_filter_too_few_selected_calls"
                ep_stat["quality_tier"] = "reject"
                ep_stat["quality_score"] = 0.0
                stats["per_episode"].append(ep_stat)
                stats["rejected"] += 1
                _save_checkpoint(
                    output_dir, checkpoint, source_ep=ep_name,
                    status="skipped_post_filter",
                    replay_dir="",
                    quality_tier="reject",
                    quality_score=0.0,
                )
                continue

            stats["per_episode"].append(ep_stat)

            if result.accepted:
                stats["accepted"] += 1
            else:
                stats["rejected"] += 1

            tier = ep_stat["quality_tier"]
            if tier in stats["quality_distribution"]:
                stats["quality_distribution"][tier] += 1

            # ── Real-time quality-gated registry update ──
            _update_replay_registry(
                registry_dir=output_dir / "trajs2data_replay_synthesis",
                episode_name=saved_dir_name,
                quality_tier=tier,
                quality_score=ep_stat["quality_score"],
                accepted=result.accepted,
                task_type=task_type,
                num_steps=ep_stat["tool_steps"],
                problem_spec=result.problem_spec,
                min_quality_tier=runner_cfg.min_quality_tier,
                source_episode=ep_name,
            )

            # ── Real-time aggregated training data (JSONL) ──
            tier_rank = {"high_quality": 2, "acceptable": 1, "reject": 0}
            if result.review_record is not None and tier_rank.get(tier, -1) >= tier_rank.get(runner_cfg.min_quality_tier, 1):
                _append_review_to_jsonl(
                    data_dir=output_dir / "trajs2data_replay_synthesis",
                    review_record=result.review_record,
                )

            # ── Checkpoint: mark source episode as processed ──
            _save_checkpoint(
                output_dir,
                checkpoint,
                source_ep=ep_name,
                status="accepted" if result.accepted else "rejected",
                replay_dir=saved_dir_name,
                quality_tier=tier,
                quality_score=ep_stat["quality_score"],
            )

            logger.info(
                "  accepted=%s  tier=%s  score=%.2f  steps=%d",
                result.accepted, tier, ep_stat["quality_score"], ep_stat["tool_steps"],
            )

        except Exception:
            logger.error("Error processing %s", ep_name, exc_info=True)
            stats["errored"] += 1
            stats["per_episode"].append({
                "episode": ep_name,
                "accepted": False,
                "rejected_reason": "exception",
                "traceback": traceback.format_exc(),
            })
            # ── Checkpoint: mark source episode as errored ──
            _save_checkpoint(
                output_dir,
                checkpoint,
                source_ep=ep_name,
                status="error",
                error=traceback.format_exc()[:500],
            )

    # ── Save summary ──
    summary_path = output_dir / "replay_synthesis_summary.json"
    _atomic_write_json(summary_path, stats)
    logger.info("Summary saved to %s", summary_path)

    return stats


# ── CLI ──────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Replay Synthesis from Raw Exploration Episodes"
    )
    p.add_argument(
        "--input", required=True,
        help="Directory containing raw exploration episodes (trajs2data_raw/...)"
    )
    p.add_argument(
        "--config", required=True,
        help="Path to the world config YAML (e.g. configs/egts/tool_sandbox.yaml)"
    )
    p.add_argument(
        "--output", default="./output/replay_synthesis_from_raw",
        help="Output directory for synthesized replay episodes"
    )
    p.add_argument(
        "--limit", type=int, default=0,
        help="Max episodes to process (0 = all)"
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Discover and validate without executing"
    )
    p.add_argument(
        "--no-resume", action="store_true",
        help="Do not skip already-processed episodes (re-process all)"
    )
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config = load_config(args.config)
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        logger.error("Input directory not found: %s", input_dir)
        sys.exit(1)

    stats = await run_replay_on_raw_episodes(
        input_dir=input_dir,
        config=config,
        output_dir=output_dir,
        limit=args.limit,
        dry_run=args.dry_run,
        resume=not args.no_resume,
    )

    print()
    print("=== Replay Synthesis Complete ===")
    print(f"  Total:    {stats['total']}")
    print(f"  Accepted: {stats['accepted']}")
    print(f"  Rejected: {stats['rejected']}")
    print(f"  Errored:  {stats['errored']}")
    print(f"  Quality:  {stats['quality_distribution']}")
    print(f"  Output:   {output_dir}")


if __name__ == "__main__":
    asyncio.run(_main())
