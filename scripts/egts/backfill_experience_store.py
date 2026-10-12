#!/usr/bin/env python
"""Backfill EGTS experience stores from existing raw trajectory episodes."""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EGTS_ROOT = PROJECT_ROOT / "src" / "egts"
if str(EGTS_ROOT) not in sys.path:
    sys.path.insert(0, str(EGTS_ROOT))

from data_collection.experience.experience_manager import create_experience_manager
from data_collection.maas_client import MaaSClient
from data_collection.utils.config import load_config


logger = logging.getLogger(__name__)


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _iter_raw_episode_dirs(input_dir: Path) -> Iterable[Path]:
    raw_dir = input_dir / "trajs2data_raw"
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw episode directory not found: {raw_dir}")

    for episode_dir in sorted(raw_dir.iterdir()):
        if not episode_dir.is_dir():
            continue
        if (episode_dir / "trajectory.json").exists() and (
            episode_dir / "raw_context.json"
        ).exists():
            yield episode_dir


def _extract_reset_meta(raw_context: Dict[str, Any]) -> Dict[str, Any]:
    world_context = raw_context.get("world_context")
    if not isinstance(world_context, dict):
        return {}
    reset = world_context.get("reset")
    if not isinstance(reset, dict):
        return {}
    metadata = reset.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    episode_meta = metadata.get("episode_reset_meta")
    return episode_meta if isinstance(episode_meta, dict) else {}


def _build_problem(
    raw_context: Dict[str, Any],
    metadata: Dict[str, Any],
    trajectory: Dict[str, Any],
    *,
    use_reset_task_instruction: bool = False,
) -> Dict[str, Any]:
    reset_meta = _extract_reset_meta(raw_context)
    task_instruction = (
        reset_meta.get("task_instruction") if use_reset_task_instruction else None
    )
    task_key = reset_meta.get("task_key") or reset_meta.get("task_id")

    if task_instruction:
        problem = str(task_instruction)
    else:
        domain = (
            metadata.get("task_domain")
            or raw_context.get("task_domain")
            or metadata.get("mcp_server")
            or "executable world"
        )
        task_type = metadata.get("task_type") or raw_context.get("task_type") or "task"
        tools_used = trajectory.get("tools_used") or [
            tc.get("tool_name")
            for tc in trajectory.get("tool_calls", [])
            if isinstance(tc, dict) and tc.get("tool_name")
        ]
        tool_summary = (
            f" using observed tools: {', '.join(str(t) for t in tools_used[:8])}"
            if tools_used
            else ""
        )
        problem = (
            f"Summarize the reusable operational pattern from an executed "
            f"{task_type} trajectory in {domain}{tool_summary}."
        )

    experience_context = {
        "world_id": metadata.get("output_namespace") or reset_meta.get("output_namespace"),
        "world_domain": reset_meta.get("selected_domain")
        or metadata.get("task_domain")
        or raw_context.get("task_domain"),
        "task_type": metadata.get("task_type") or raw_context.get("task_type"),
        "stage": metadata.get("stage"),
        "tier": metadata.get("tier"),
        "phase": metadata.get("phase"),
        "visible_tools": raw_context.get("tools_allowed") or metadata.get("tools_allowed"),
        "successful_tools": trajectory.get("tools_used"),
        "anchor_usage": raw_context.get("anchor_usage") or metadata.get("anchor_usage"),
        "state_evidence": raw_context.get("state_evidence") or metadata.get("state_evidence"),
        "retrieval_summary": (
            raw_context.get("retrieval_spec", {}) or {}
        ).get("summary")
        if isinstance(raw_context.get("retrieval_spec"), dict)
        else None,
    }
    experience_context = {
        k: v for k, v in experience_context.items() if v not in (None, "", [], {})
    }
    experience_metadata = {
        "episode_id": metadata.get("iteration"),
        "pipeline_mode": metadata.get("pipeline_mode", "trajs2data_raw"),
        "task_type": metadata.get("task_type") or raw_context.get("task_type"),
        "stage": metadata.get("stage"),
        "tier": metadata.get("tier"),
        "phase": metadata.get("phase"),
        "world_domain": experience_context.get("world_domain"),
        "data_source": metadata.get("data_source"),
        "output_namespace": metadata.get("output_namespace")
        or reset_meta.get("output_namespace"),
    }
    experience_metadata = {
        k: v for k, v in experience_metadata.items() if v not in (None, "", [], {})
    }

    return {
        "problem": problem,
        "task_key": task_key,
        "repository_url": reset_meta.get("repository_url"),
        "data_source": metadata.get("data_source"),
        "experience_context": experience_context,
        "experience_metadata": experience_metadata,
    }


def _load_progress(path: Path, reset: bool) -> Set[str]:
    if reset or not path.exists():
        return set()
    try:
        data = _load_json(path)
        processed = data.get("processed_episodes", [])
        return set(str(item) for item in processed)
    except Exception as exc:
        logger.warning("Failed to load progress file %s: %s", path, exc)
        return set()


def _save_progress(path: Path, processed: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"processed_count": len(processed), "processed_episodes": sorted(processed)},
            f,
            indent=2,
            ensure_ascii=False,
        )


async def backfill(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    maas_client = MaaSClient(config.maas)

    input_dir = Path(args.input_dir) if args.input_dir else Path(config.pipeline.output_dir) / config.pipeline.exp_name
    input_dir = input_dir.resolve()

    experience_manager = create_experience_manager(
        config=config.trajs2data,
        maas_client=maas_client,
        output_dir=input_dir,
        model_config=config.get_nl_rewrite_model_config(),
    )
    if experience_manager is None:
        raise RuntimeError(
            "experience_manager is disabled in config; enable trajs2data.experience_manager first."
        )

    progress_path = (
        Path(args.progress_file)
        if args.progress_file
        else input_dir / "experience_backfill_progress.json"
    )
    processed = _load_progress(progress_path, reset=args.reset_progress)

    attempted = 0
    extracted = 0
    skipped = 0

    for episode_dir in _iter_raw_episode_dirs(input_dir):
        episode_id = episode_dir.name
        if episode_id in processed:
            skipped += 1
            continue
        if args.limit is not None and attempted >= args.limit:
            break

        trajectory = _load_json(episode_dir / "trajectory.json")
        raw_context = _load_json(episode_dir / "raw_context.json")
        metadata = (
            _load_json(episode_dir / "metadata.json")
            if (episode_dir / "metadata.json").exists()
            else {}
        )
        problem = _build_problem(
            raw_context,
            metadata,
            trajectory,
            use_reset_task_instruction=args.use_reset_task_instruction,
        )

        attempted += 1
        skill = await experience_manager.on_episode_success(
            trajectory=trajectory,
            problem=problem,
            metadata=problem.get("experience_metadata"),
        )
        if skill is not None:
            extracted += 1
        processed.add(episode_id)

        if attempted % args.save_every == 0:
            experience_manager.save()
            _save_progress(progress_path, processed)
            logger.info(
                "Backfill progress: attempted=%s extracted=%s skipped=%s",
                attempted,
                extracted,
                skipped,
            )

    experience_manager.save()
    _save_progress(progress_path, processed)
    logger.info(
        "Backfill complete: attempted=%s extracted=%s skipped=%s store=%s",
        attempted,
        extracted,
        skipped,
        experience_manager.experience_store.store_path,
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract EGTS experience entries from existing raw episodes."
    )
    parser.add_argument("--config", required=True, help="Path to EGTS collection config.")
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Experiment output directory. Defaults to pipeline.output_dir/pipeline.exp_name.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of unprocessed raw episodes to backfill.",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=10,
        help="Persist store/progress after this many attempted episodes.",
    )
    parser.add_argument(
        "--progress-file",
        default=None,
        help="Optional progress JSON path. Defaults to input-dir/experience_backfill_progress.json.",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="Ignore existing backfill progress and revisit raw episodes.",
    )
    parser.add_argument(
        "--use-reset-task-instruction",
        action="store_true",
        help=(
            "Use executable-world reset task_instruction when present. "
            "Disabled by default to keep experience extraction grounded only in observed trajectories."
        ),
    )
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    raise SystemExit(asyncio.run(backfill(args)))


if __name__ == "__main__":
    main()
