import asyncio
import copy
import glob
import json
import logging
import os
import re
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if __package__ in {None, ""}:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

from data_collection.maas_client import MaaSClient
from data_collection.problem_synthesizer import (
    IntentSpec,
    RetrievalSpec,
    TaskCategory,
    TaskType,
    build_retrieval_spec,
    rewrite_retrieval_to_problem_json,
    rewrite_to_problem_json,
    rewrite_trajectory_thoughts,
)
from data_collection.trajs2data_collector import (
    EpisodeStatus,
    StrictTrajectory,
    ToolCallRecord,
)
from data_collection.utils.config import SingleModelConfig, load_config
from data_synthesis.io_sanitizer import IOSanitizerMixin
from data_synthesis.quality_gate import evaluate_tool_quality
from data_synthesis.stage1_candidates import (
    extract_problem_candidates,
    select_problem_candidate,
)
from data_synthesis.stage1_problem import Stage1ProblemMixin
from data_synthesis.stage2_trajectory import Stage2TrajectoryMixin
from data_synthesis.synthesis_dedup import (
    SynthesisDeduplicator,
    create_synthesis_deduplicator,
)
from prompts import PromptLoader
from prompts import trajectory_fallback as fallback_prompts

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = fallback_prompts.SYNTHESIS_SYSTEM_PROMPT


class InputMode(str, Enum):
    AUTO = "auto"
    RAW = "raw"
    SYNTHESIZED = "synthesized"


class DataSynthesisPipeline(
    Stage1ProblemMixin,
    Stage2TrajectoryMixin,
    IOSanitizerMixin,
):
    def __init__(self, config_path: str = "configs/egts/config.yaml"):
        self.config_path = config_path
        self.config = load_config(config_path)
        self.client = MaaSClient(self.config.maas)
        models_conf = self.config.maas.models
        try:
            self.num_workers = max(
                1, int(getattr(self.config.pipeline, "num_workers", 1) or 1)
            )
        except Exception:
            self.num_workers = 1

        # Resolve judge model: prefer synthesis-specific "judge_model" key,
        # fall back to collection-style "trajectory_collection" for backward compat.
        judge_cfg = getattr(models_conf, "judge_model", None) or models_conf.trajectory_collection
        self.judge_model = SingleModelConfig(
            model=judge_cfg.model,
            temperature=0.1,
            base_url=judge_cfg.base_url,
            api_key=judge_cfg.api_key,
            max_tokens=judge_cfg.max_tokens,
        )

        # Resolve rewrite model: prefer synthesis-specific "synthesis_model" key,
        # fall back to collection-style "nl_rewrite", then judge model.
        rewrite_cfg = getattr(models_conf, "synthesis_model", None) or models_conf.nl_rewrite
        if rewrite_cfg:
            self.rewrite_model = rewrite_cfg
        else:
            self.rewrite_model = SingleModelConfig(
                model=judge_cfg.model,
                temperature=0.7,
                base_url=judge_cfg.base_url,
                api_key=judge_cfg.api_key,
                max_tokens=judge_cfg.max_tokens,
            )

        ds_cfg = getattr(self.config.trajs2data, "data_synthesis", None)
        if ds_cfg is None:
            from data_collection.config.trajs2data import DataSynthesisConfig

            ds_cfg = DataSynthesisConfig()
        self.max_problem_refine_loops = self._resolve_loop_count(
            ds_cfg.max_problem_refine_loops, fallback=3
        )
        self.max_trajectory_refine_loops = self._resolve_loop_count(
            ds_cfg.max_trajectory_refine_loops, fallback=3
        )
        self.require_planning_step = bool(ds_cfg.require_planning_step)
        self.require_final_answer = bool(ds_cfg.require_final_answer)
        self.min_step_coverage_ratio = float(
            max(0.5, min(1.0, ds_cfg.min_step_coverage_ratio))
        )
        self.enable_heuristic_fallback = bool(ds_cfg.enable_heuristic_fallback)
        self.save_llm_io = bool(ds_cfg.save_llm_io)
        self.llm_io_file = str(ds_cfg.llm_io_file or "").strip()
        self.llm_io_include_prompts = bool(ds_cfg.llm_io_include_prompts)
        self.llm_io_max_text_chars = int(ds_cfg.llm_io_max_text_chars or 0)
        self.rewrite_context_max_chars = int(
            ds_cfg.rewrite_context_max_chars or 5000
        )
        self.rewrite_tool_sequence_max_steps = int(
            ds_cfg.rewrite_tool_sequence_max_steps or 40
        )
        self.rewrite_segment_size = int(
            getattr(ds_cfg, "rewrite_segment_size", None) or 6
        )
        self.compress_tool_sequence = bool(
            getattr(ds_cfg, "compress_tool_sequence", None) or False
        )
        self.compress_min_keep_ratio = float(
            max(0.3, min(1.0, getattr(ds_cfg, "compress_min_keep_ratio", None) or 0.5))
        )
        self.skip_invalid_structure = bool(ds_cfg.skip_invalid_structure)
        self.reject_failure_only_tools = bool(ds_cfg.reject_failure_only_tools)
        self.max_tool_failure_rate = float(
            max(0.0, min(1.0, ds_cfg.max_tool_failure_rate))
        )
        self.rewrite_context_max_chars = max(500, min(50000, self.rewrite_context_max_chars))
        self.rewrite_tool_sequence_max_steps = max(
            3, min(300, self.rewrite_tool_sequence_max_steps)
        )

        # Phase 1: Dual-judge configuration
        self.use_dual_judge = bool(ds_cfg.use_dual_judge)
        # Soft judge remains advisory in acceptance logic; threshold is retained for future use.
        self.soft_judge_threshold = float(max(0.0, min(1.0, ds_cfg.soft_judge_threshold)))

        # Phase 2: Fallback+polish configuration
        self.trajectory_mode = str(ds_cfg.trajectory_mode or "llm_rewrite").lower()
        if self.trajectory_mode not in ("llm_rewrite", "fallback_polish", "fallback_only"):
            logger.warning(
                "Invalid trajectory_mode '%s', falling back to 'llm_rewrite'",
                self.trajectory_mode,
            )
            self.trajectory_mode = "llm_rewrite"
        self.max_polish_loops = self._resolve_loop_count(ds_cfg.max_polish_loops, fallback=3)
        self.polish_model = self._resolve_polish_model_config(
            str(ds_cfg.polish_model or "synthesis_model"),
            base_judge=judge_cfg,
            rewrite_model=self.rewrite_model,
            models_conf=models_conf,
        )

        # Relaxed judge model for fallback_polish path (higher temperature to avoid overly rigid rejection)
        relaxed_temp = float(getattr(ds_cfg, "judge_temperature_relaxed", 0.3))
        self.judge_model_relaxed = SingleModelConfig(
            model=judge_cfg.model,
            temperature=relaxed_temp,
            base_url=judge_cfg.base_url,
            api_key=judge_cfg.api_key,
            max_tokens=judge_cfg.max_tokens,
        )
        self.quality_policy = str(ds_cfg.quality_policy or "legacy_all").lower()
        if self.quality_policy not in {"legacy_all", "high_and_acceptable", "high_only"}:
            logger.warning(
                "Invalid quality_policy '%s', falling back to legacy_all",
                self.quality_policy,
            )
            self.quality_policy = "legacy_all"
        self.quality_gate_enabled = bool(ds_cfg.quality_gate_enabled)
        self.fallback_for_training = bool(ds_cfg.fallback_for_training)
        self.fallback_min_tool_steps = int(max(1, ds_cfg.fallback_min_tool_steps))
        self.quality_score_enabled = bool(ds_cfg.quality_score_enabled)
        self.min_quality_score_high = float(max(0.0, min(1.0, ds_cfg.min_quality_score_high)))
        self.min_quality_score_acceptable = float(
            max(0.0, min(1.0, ds_cfg.min_quality_score_acceptable))
        )
        if self.min_quality_score_acceptable > self.min_quality_score_high:
            logger.warning(
                "min_quality_score_acceptable %.2f > min_quality_score_high %.2f; clamping acceptable to high",
                self.min_quality_score_acceptable,
                self.min_quality_score_high,
            )
            self.min_quality_score_acceptable = self.min_quality_score_high
        self.quality_shadow_report = bool(ds_cfg.quality_shadow_report)

        # Pre-screening (fast metadata-only filter before parallel synthesis)
        self.pre_screening_enabled = bool(
            getattr(ds_cfg, "pre_screening_enabled", True)
        )
        self.pre_screening_min_tool_calls = int(
            getattr(ds_cfg, "pre_screening_min_tool_calls", 2)
        )
        self.pre_screening_min_distinct_tools = int(
            getattr(ds_cfg, "pre_screening_min_distinct_tools", 1)
        )
        self.episode_timeout_seconds = int(
            getattr(ds_cfg, "episode_timeout_seconds", 600)
        )

        # Dataset-level deduplication
        self._dedup: Optional[SynthesisDeduplicator] = create_synthesis_deduplicator(
            ds_cfg=ds_cfg,
            maas_cfg=self.config.maas if hasattr(self.config, "maas") else None,
        )
        if self._dedup:
            logger.info(
                "Dataset-level dedup enabled: mode=%s", self._dedup.mode
            )

        self._active_episode_context: Dict[str, Any] = {}
        self._active_call_context: Dict[str, Any] = {}
        self._episode_llm_calls: List[Dict[str, Any]] = []
        if self.save_llm_io:
            self.client.set_completion_observer(self._on_llm_completion)

    @staticmethod
    def _resolve_loop_count(value: Any, fallback: int = 3) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = fallback
        return max(1, min(10, parsed))

    @staticmethod
    def _resolve_polish_model_config(
        polish_model_name: str,
        *,
        base_judge: SingleModelConfig,
        rewrite_model: SingleModelConfig,
        models_conf: Any,
    ) -> SingleModelConfig:
        alias = str(polish_model_name or "").strip().lower()
        if alias in {"", "synthesis_model", "nl_rewrite"}:
            cfg = getattr(models_conf, "synthesis_model", None) or getattr(models_conf, "nl_rewrite", None)
            return cfg or rewrite_model
        if alias in {"judge_model", "trajectory_collection"}:
            return base_judge
        # Treat as literal model name and inherit endpoint/auth from rewrite model.
        return SingleModelConfig(
            model=str(polish_model_name).strip(),
            base_url=rewrite_model.base_url,
            api_key=rewrite_model.api_key,
            temperature=rewrite_model.temperature,
            max_tokens=rewrite_model.max_tokens,
        )

    # Per-world threshold multipliers: <1.0 = relaxed, >1.0 = tightened.
    _WORLD_THRESHOLD_MULTIPLIERS = {
        "terminal-bench": 0.90,  # Complex shell ops — relax thresholds
        "webshop": 1.10,         # Simpler, deterministic — tighten thresholds
    }

    @classmethod
    def _get_world_threshold_multiplier(cls, mcp_server: str = "") -> float:
        if not mcp_server:
            return 1.0
        server_lower = mcp_server.lower()
        for pattern, multiplier in cls._WORLD_THRESHOLD_MULTIPLIERS.items():
            if pattern in server_lower:
                return multiplier
        return 1.0

    def _compute_quality_signal(
        self, stage2_result: Any, tool_steps: int = 0, mcp_server: str = "",
    ) -> Dict[str, Any]:
        accept_mode = str(getattr(stage2_result, "accept_mode", "") or "")
        realistic = bool(getattr(stage2_result, "realistic", False))
        is_fallback_path = "fallback" in accept_mode.lower()
        hard_pass = bool(
            getattr(stage2_result, "hard_judge_pass", False)
            or accept_mode == "primary_judge_pass"
            or accept_mode == "dual_judge_pass"
        )
        soft_pass = bool(getattr(stage2_result, "soft_judge_pass", False))
        soft_issues = list(getattr(stage2_result, "soft_judge_issues", []) or [])

        if not realistic:
            return {
                "quality_tier": "reject",
                "quality_score": 0.0,
                "hard_judge_pass": hard_pass,
                "soft_judge_pass": soft_pass,
                "soft_judge_issues": soft_issues,
                "is_fallback_path": is_fallback_path,
            }

        score = 0.70 if hard_pass else 0.0
        if self.quality_score_enabled:
            if soft_pass:
                score += 0.20
            if soft_pass and "dual_judge_pass" in accept_mode:
                score += 0.10
            if is_fallback_path:
                # Fallback records passed structural checks but not factual judges.
                # Give a base of 0.55 (structural quality) instead of 0.0 so they
                # can qualify when fallback_for_training policy is enabled.
                if not hard_pass and score < 0.01:
                    score = 0.55
                elif self.trajectory_mode in ("fallback_polish", "fallback_only"):
                    # In fallback_polish/fallback_only mode, rule-based trajectories
                    # are the primary path — don't penalize judge-validated trajectories.
                    pass
                else:
                    score -= 0.15
        score = max(0.0, min(1.0, score))

        # Adaptive threshold: protect long trajectories with relaxed bounds.
        # threshold = max(0.60, 0.85 - 0.012 * (steps - 3))
        steps = max(0, int(tool_steps or 0))
        world_mult = self._get_world_threshold_multiplier(mcp_server)
        adaptive_high = max(0.55, (self.min_quality_score_high - 0.012 * max(0, steps - 3)) * world_mult)
        adaptive_acceptable = max(0.55, (self.min_quality_score_acceptable - 0.012 * max(0, steps - 3)) * world_mult)

        if is_fallback_path:
            if self.trajectory_mode in ("fallback_polish", "fallback_only") and hard_pass:
                # In fallback_polish/fallback_only mode, rule-based trajectories
                # are the primary path — rules generate skeletons, (optionally) LLM
                # polishes, judges validate. When judges pass, the trajectory earns
                # its quality tier by score rather than being locked to "fallback_based".
                if score >= adaptive_high:
                    quality_tier = "high_quality"
                elif score >= adaptive_acceptable:
                    quality_tier = "acceptable"
                else:
                    quality_tier = "fallback_based"
            else:
                quality_tier = "fallback_based"
        elif score >= adaptive_high:
            quality_tier = "high_quality"
        elif score >= adaptive_acceptable:
            quality_tier = "acceptable"
        else:
            quality_tier = "reject"

        return {
            "quality_tier": quality_tier,
            "quality_score": round(score, 4),
            "hard_judge_pass": hard_pass,
            "soft_judge_pass": soft_pass,
            "soft_judge_issues": soft_issues,
            "is_fallback_path": is_fallback_path,
        }

    def _decide_training_selection(
        self,
        *,
        quality_tier: str,
        quality_score: float,
        is_fallback_path: bool,
        tool_steps: int = 0,
        mcp_server: str = "",
    ) -> Tuple[bool, str]:
        policy = self.quality_policy
        if (not self.quality_gate_enabled) or policy == "legacy_all":
            return True, "legacy_or_gate_disabled"

        if self.fallback_for_training and is_fallback_path:
            if tool_steps >= self.fallback_min_tool_steps:
                return True, "fallback_allowed_by_policy"
            return False, "fallback_insufficient_steps"

        # In fallback_polish/fallback_only mode, judge-validated trajectories earn
        # their quality tier by score.  Don't let the fallback origin veto them.
        if is_fallback_path and not self.fallback_for_training:
            if (
                self.trajectory_mode in ("fallback_polish", "fallback_only")
                and quality_tier in ("high_quality", "acceptable")
            ):
                return True, f"{quality_tier}_tier_pass"

        # Compute adaptive thresholds consistent with _compute_quality_signal.
        # Longer trajectories get relaxed bounds because perfect execution is harder.
        steps = max(0, int(tool_steps or 0))
        world_mult = self._get_world_threshold_multiplier(mcp_server)
        adaptive_high = max(0.55, (self.min_quality_score_high - 0.012 * max(0, steps - 3)) * world_mult)
        adaptive_acceptable = max(0.55, (self.min_quality_score_acceptable - 0.012 * max(0, steps - 3)) * world_mult)

        if policy == "high_only":
            if quality_tier == "high_quality" and quality_score >= adaptive_high:
                return True, "high_only_pass"
            return False, "high_only_reject"

        if policy == "high_and_acceptable":
            if quality_tier == "high_quality" and quality_score >= adaptive_high:
                return True, "high_tier_pass"
            if (
                quality_tier == "acceptable"
                and quality_score >= adaptive_acceptable
            ):
                return True, "acceptable_tier_pass"
            return False, "tier_or_score_reject"

        # Guarded fallback.
        return True, "policy_fallback_allow"

    @staticmethod
    def _resolve_fallback_output_path(output_file: str) -> str:
        base, ext = os.path.splitext(output_file)
        ext = ext or ".json"
        return f"{base}_fallback{ext}"

    @staticmethod
    def _difficulty_from_tool_steps(tool_steps: int) -> Tuple[str, int]:
        steps = max(0, int(tool_steps or 0))
        if steps <= 0:
            return "unknown", 0
        if steps <= 6:
            return "easy", 1
        if steps <= 12:
            return "medium", 2
        if steps <= 20:
            return "hard", 3
        return "expert", 4

    def _difficulty_fields(self, tool_steps: int) -> Dict[str, Any]:
        level, rank = self._difficulty_from_tool_steps(tool_steps)
        return {
            "difficulty_tool_steps": max(0, int(tool_steps or 0)),
            "difficulty_level": level,
            "difficulty_rank": rank,
        }

    @staticmethod
    def _load_json_list(path: str) -> List[Dict[str, Any]]:
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    @staticmethod
    def _save_json_atomic(path: str, data: List[Dict[str, Any]]) -> None:
        if not path:
            return
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_synthesis_", suffix=".json", dir=parent or ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _resolve_llm_io_path(self, output_file: str) -> str:
        configured = (self.llm_io_file or "").strip()
        if configured:
            if os.path.isabs(configured):
                return configured
            return os.path.abspath(configured)
        base_dir = os.path.dirname(os.path.abspath(output_file))
        return os.path.join(base_dir, "synthesis_llm_io.json")

    def _truncate_for_trace(self, value: Any) -> Any:
        if self.llm_io_max_text_chars <= 0:
            return value
        if isinstance(value, str):
            if len(value) <= self.llm_io_max_text_chars:
                return value
            keep = max(0, self.llm_io_max_text_chars - 3)
            return value[:keep] + "..."
        if isinstance(value, list):
            return [self._truncate_for_trace(v) for v in value]
        if isinstance(value, dict):
            return {k: self._truncate_for_trace(v) for k, v in value.items()}
        return value

    def _set_call_context(self, **kwargs: Any) -> None:
        self._active_call_context = dict(kwargs)

    def _clear_call_context(self) -> None:
        self._active_call_context = {}

    def _on_llm_completion(self, payload: Dict[str, Any]) -> None:
        if not self.save_llm_io:
            return

        entry: Dict[str, Any] = {
            "timestamp": payload.get("timestamp"),
            "model": payload.get("model"),
            "base_url": payload.get("base_url"),
            "temperature": payload.get("temperature"),
            "max_tokens": payload.get("max_tokens"),
            "messages_count": payload.get("messages_count"),
            "request_chars": payload.get("request_chars"),
            "response_chars": payload.get("response_chars"),
            "tool_calls_count": payload.get("tool_calls_count"),
            "finish_reason": payload.get("finish_reason"),
            "usage": payload.get("usage"),
            "latency_ms": payload.get("latency_ms"),
            "tools_provided": payload.get("tools_provided"),
            "error": payload.get("error"),
        }
        entry.update(self._active_episode_context)
        entry.update(self._active_call_context)

        if self.llm_io_include_prompts:
            entry["messages"] = payload.get("messages", [])
            entry["response_content"] = payload.get("response_content", "")
        if self.llm_io_max_text_chars > 0:
            entry = self._truncate_for_trace(entry)

        self._episode_llm_calls.append(entry)

    def _build_episode_llm_trace_record(
        self,
        episode_dir: str,
        mode: str,
        accepted: bool,
        stage: str,
        error: str = "",
    ) -> Dict[str, Any]:
        sanitized_episode_dir = self._sanitize_content(episode_dir, episode_dir)
        sanitized_llm_calls = self._sanitize_content(
            list(self._episode_llm_calls), episode_dir
        )
        return {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "episode_dir": sanitized_episode_dir,
            "mode": mode,
            "accepted": accepted,
            "stage": stage,
            "error": self._sanitize_content(error, episode_dir),
            "llm_calls": sanitized_llm_calls,
        }

    def _validate_trajectory_structure(
        self, traj_data: Dict[str, Any]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        messages = traj_data.get("messages")
        if not isinstance(messages, list):
            return (
                False,
                "trajectory.messages is missing or not a list",
                {
                    "assistant_tool_calls": 0,
                    "tool_messages": 0,
                    "trajectory_tool_calls": 0,
                    "missing_call_id": 0,
                },
            )

        assistant_call_ids: List[str] = []
        tool_message_ids: List[str] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = str(msg.get("role", ""))
            if role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                if not isinstance(tool_calls, list):
                    return (
                        False,
                        "assistant message tool_calls is not a list",
                        {
                            "assistant_tool_calls": len(assistant_call_ids),
                            "tool_messages": len(tool_message_ids),
                            "trajectory_tool_calls": 0,
                            "missing_call_id": 0,
                        },
                    )
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    call_id = tc.get("id")
                    if call_id:
                        assistant_call_ids.append(str(call_id))
            elif role == "tool":
                call_id = msg.get("tool_call_id")
                if call_id:
                    tool_message_ids.append(str(call_id))

        if len(set(assistant_call_ids)) != len(assistant_call_ids):
            return (
                False,
                "duplicate assistant tool_call ids",
                {
                    "assistant_tool_calls": len(assistant_call_ids),
                    "tool_messages": len(tool_message_ids),
                    "trajectory_tool_calls": 0,
                    "missing_call_id": 0,
                },
            )
        if len(set(tool_message_ids)) != len(tool_message_ids):
            return (
                False,
                "duplicate tool message tool_call_id",
                {
                    "assistant_tool_calls": len(assistant_call_ids),
                    "tool_messages": len(tool_message_ids),
                    "trajectory_tool_calls": 0,
                    "missing_call_id": 0,
                },
            )
        if len(assistant_call_ids) != len(tool_message_ids):
            return (
                False,
                f"assistant/tool count mismatch ({len(assistant_call_ids)} vs {len(tool_message_ids)})",
                {
                    "assistant_tool_calls": len(assistant_call_ids),
                    "tool_messages": len(tool_message_ids),
                    "trajectory_tool_calls": 0,
                    "missing_call_id": 0,
                },
            )
        if set(assistant_call_ids) != set(tool_message_ids):
            return (
                False,
                "assistant/tool id sets mismatch",
                {
                    "assistant_tool_calls": len(assistant_call_ids),
                    "tool_messages": len(tool_message_ids),
                    "trajectory_tool_calls": 0,
                    "missing_call_id": 0,
                },
            )

        raw_tool_calls = traj_data.get("tool_calls", [])
        trajectory_tool_call_ids: List[str] = []
        missing_call_id = 0
        success_actual = 0
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            for tc in raw_tool_calls:
                if not isinstance(tc, dict):
                    continue
                call_id = tc.get("call_id")
                if call_id:
                    trajectory_tool_call_ids.append(str(call_id))
                else:
                    missing_call_id += 1
                if tc.get("success") is True:
                    success_actual += 1

            if missing_call_id > 0:
                return (
                    False,
                    f"trajectory.tool_calls has {missing_call_id} entries missing call_id",
                    {
                        "assistant_tool_calls": len(assistant_call_ids),
                        "tool_messages": len(tool_message_ids),
                        "trajectory_tool_calls": len(trajectory_tool_call_ids),
                        "missing_call_id": missing_call_id,
                    },
                )
            if len(trajectory_tool_call_ids) != len(tool_message_ids):
                return (
                    False,
                    "trajectory.tool_calls/tool messages count mismatch "
                    f"({len(trajectory_tool_call_ids)} vs {len(tool_message_ids)})",
                    {
                        "assistant_tool_calls": len(assistant_call_ids),
                        "tool_messages": len(tool_message_ids),
                        "trajectory_tool_calls": len(trajectory_tool_call_ids),
                        "missing_call_id": missing_call_id,
                    },
                )
            if set(trajectory_tool_call_ids) != set(tool_message_ids):
                return (
                    False,
                    "trajectory.tool_calls ids and tool message ids mismatch",
                    {
                        "assistant_tool_calls": len(assistant_call_ids),
                        "tool_messages": len(tool_message_ids),
                        "trajectory_tool_calls": len(trajectory_tool_call_ids),
                        "missing_call_id": missing_call_id,
                    },
                )

            success_field = int(traj_data.get("num_successful_tool_calls", 0) or 0)
            if success_field != success_actual:
                return (
                    False,
                    "num_successful_tool_calls mismatch "
                    f"(field={success_field}, actual={success_actual})",
                    {
                        "assistant_tool_calls": len(assistant_call_ids),
                        "tool_messages": len(tool_message_ids),
                        "trajectory_tool_calls": len(trajectory_tool_call_ids),
                        "missing_call_id": missing_call_id,
                    },
                )

        return (
            True,
            "",
            {
                "assistant_tool_calls": len(assistant_call_ids),
                "tool_messages": len(tool_message_ids),
                "trajectory_tool_calls": len(trajectory_tool_call_ids),
                "missing_call_id": missing_call_id,
            },
        )

    def _build_structure_rejection_meta(
        self,
        *,
        source_mode: str,
        episode_dir: str,
        task_type: str,
        mcp_server: str,
        rejected_reason: str,
        structure_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        inferred_steps = int(
            max(
                structure_stats.get("trajectory_tool_calls", 0) or 0,
                structure_stats.get("assistant_tool_calls", 0) or 0,
            )
        )
        return {
            "id": str(uuid.uuid4()),
            "source_mode": source_mode,
            "episode_dir": episode_dir,
            "accepted": False,
            "task_type": task_type,
            "mcp_server": mcp_server,
            "rejected_stage": "trajectory_structure_gate",
            "rejected_reason": rejected_reason,
            "problem_accept_mode": "unaccepted",
            "trajectory_accept_mode": "unaccepted",
            "problem_refine_attempts": 0,
            "trajectory_refine_attempts": 0,
            "problem_last_failure_reason": "N/A",
            "trajectory_last_failure_reason": rejected_reason,
            "fallback_used": False,
            "quality_tier": "reject",
            "quality_score": 0.0,
            "hard_judge_pass": False,
            "soft_judge_pass": False,
            "soft_judge_issues": [],
            "selected_for_training": False,
            "structure_gate_enabled": bool(self.skip_invalid_structure),
            "trajectory_structure_stats": structure_stats,
            **self._difficulty_fields(inferred_steps),
        }

    def _run_tool_quality_gate(
        self, traj_data: Dict[str, Any]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        ordered_tool_calls = self._extract_tool_calls_for_rewrite(
            traj_data, traj_data.get("messages", [])
        )
        passed, reason, stats = evaluate_tool_quality(
            ordered_tool_calls,
            reject_failure_only_tools=self.reject_failure_only_tools,
            max_tool_failure_rate=self.max_tool_failure_rate,
        )
        stats = {
            **(stats or {}),
            "reject_failure_only_tools_enabled": bool(self.reject_failure_only_tools),
            "max_tool_failure_rate_limit": float(self.max_tool_failure_rate),
        }
        return passed, reason, stats

    def _build_tool_quality_rejection_meta(
        self,
        *,
        source_mode: str,
        episode_dir: str,
        task_type: str,
        mcp_server: str,
        rejected_reason: str,
        quality_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        inferred_steps = int(quality_stats.get("total_calls", 0) or 0)
        return {
            "id": str(uuid.uuid4()),
            "source_mode": source_mode,
            "episode_dir": episode_dir,
            "accepted": False,
            "task_type": task_type,
            "mcp_server": mcp_server,
            "rejected_stage": "trajectory_quality_gate",
            "rejected_reason": rejected_reason,
            "problem_accept_mode": "unaccepted",
            "trajectory_accept_mode": "unaccepted",
            "problem_refine_attempts": 0,
            "trajectory_refine_attempts": 0,
            "problem_last_failure_reason": "N/A",
            "trajectory_last_failure_reason": rejected_reason,
            "fallback_used": False,
            "quality_tier": "reject",
            "quality_score": 0.0,
            "hard_judge_pass": False,
            "soft_judge_pass": False,
            "soft_judge_issues": [],
            "selected_for_training": False,
            "tool_quality_gate_enabled": True,
            "trajectory_quality_stats": quality_stats,
            **self._difficulty_fields(inferred_steps),
        }

    def _pre_screen_episode(
        self, episode_dir: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Apply fast metadata-only heuristics to reject unproductive episodes.

        Reads metadata.json ONLY (not trajectory.json or raw_context.json).
        No LLM calls. Target: <1ms per episode.

        Returns (passed, reject_reason, signal_meta_dict).
        """
        meta_path = os.path.join(episode_dir, "metadata.json")
        if not os.path.isfile(meta_path):
            return (True, "", {})

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                md = json.load(f)
        except Exception:
            return (True, "", {})

        signals = md.get("quality_signals", {}) or {}
        tool_usage = signals.get("tool_usage", {}) or {}
        state_info = signals.get("state", {}) or {}
        quality_bucket = str(signals.get("quality_bucket", "") or "")
        ckpt_stats = md.get("checkpoint_stats", {}) or {}

        total_calls = int(tool_usage.get("total_tool_calls", 0) or 0)
        distinct_tools = int(tool_usage.get("distinct_tools_attempted", 0) or 0)
        mutation_calls = int(tool_usage.get("mutation_tool_calls", 0) or 0)
        state_changed = bool(state_info.get("changed", True))
        total_failures = int(ckpt_stats.get("total_failures", 0) or 0)

        meta = {
            "pre_screen_total_tool_calls": total_calls,
            "pre_screen_distinct_tools": distinct_tools,
            "pre_screen_mutation_tool_calls": mutation_calls,
            "pre_screen_state_changed": state_changed,
            "pre_screen_quality_bucket": quality_bucket,
            "pre_screen_checkpoint_failures": total_failures,
        }

        # Heuristic 1: No state change AND shallow quality bucket.
        # For API worlds (postgres, github, etc.), state_evidence.changed
        # is always False — even for legitimate deep_retrieval episodes — because
        # there's no filesystem-like diff. So we only reject when the quality
        # bucket ALSO indicates shallowness.
        if not state_changed and quality_bucket == "shallow_retrieval_or_partial":
            return (False, "no_state_changes", meta)

        # Heuristic 2: Too few total tool calls
        if total_calls < self.pre_screening_min_tool_calls:
            return (False, f"too_few_tool_calls:{total_calls}<{self.pre_screening_min_tool_calls}", meta)

        # Heuristic 3: Too few distinct tools (degenerate single-tool)
        if distinct_tools < self.pre_screening_min_distinct_tools:
            return (False, f"too_few_distinct_tools:{distinct_tools}<{self.pre_screening_min_distinct_tools}", meta)

        # Heuristic 4: Quality bucket explicitly flagged as shallow/low-quality.
        # "state_changed_without_known_mutation_tool" is NOT rejected here -
        # it means the world changed but the framework doesn't classify its
        # tools as mutation/read. This is normal for many worlds (discovery, etc.).
        if quality_bucket == "shallow_retrieval_or_partial":
            return (False, f"low_quality_bucket:{quality_bucket}", meta)

        # Heuristic 5: Excessive checkpoint failures (unstable trajectory)
        if total_failures >= 10:
            return (False, f"excessive_failures:{total_failures}", meta)

        return (True, "", meta)

    def _discover_episodes(self, input_dir: str, input_mode: str) -> List[Dict[str, str]]:
        mode = (input_mode or InputMode.AUTO.value).lower()
        include_synthesized = mode in {InputMode.AUTO.value, InputMode.SYNTHESIZED.value}
        include_raw = mode in {InputMode.AUTO.value, InputMode.RAW.value}

        episodes_by_dir: Dict[str, str] = {}

        if include_synthesized:
            synthesized_pattern = os.path.join(
                input_dir, "**", "trajs2data", "*", "problem.json"
            )
            for problem_file in glob.glob(synthesized_pattern, recursive=True):
                episode_dir = os.path.dirname(problem_file)
                episodes_by_dir[episode_dir] = InputMode.SYNTHESIZED.value

        if include_raw:
            raw_pattern = os.path.join(input_dir, "**", "trajs2data_raw", "*", "raw_context.json")
            for raw_context_file in glob.glob(raw_pattern, recursive=True):
                episode_dir = os.path.dirname(raw_context_file)
                # If both exist, prioritize pre-synthesized trajectory directories.
                episodes_by_dir.setdefault(episode_dir, InputMode.RAW.value)

        episodes = [
            {"mode": mode_name, "episode_dir": episode_dir}
            for episode_dir, mode_name in episodes_by_dir.items()
        ]
        episodes.sort(key=lambda x: x["episode_dir"])
        return episodes

    async def _process_episode_item(self, item: Dict[str, str]) -> Dict[str, Any]:
        episode_dir = item["episode_dir"]
        mode = item["mode"]
        record: Optional[Dict[str, Any]] = None
        meta: Optional[Dict[str, Any]] = None
        episode_error = ""
        started_at = time.perf_counter()

        self._active_episode_context = {
            "episode_dir": episode_dir,
            "source_mode": mode,
        }
        self._active_call_context = {}
        self._episode_llm_calls = []

        try:
            if mode == InputMode.RAW.value:
                record, meta = await self.process_raw_episode(episode_dir)
            else:
                record, meta = await self.process_episode(episode_dir)
        except Exception as e:
            episode_error = str(e)
            logger.error("Error processing %s (%s): %s", episode_dir, mode, e, exc_info=True)

        trace_record: Optional[Dict[str, Any]] = None
        if self.save_llm_io:
            trace_record = self._build_episode_llm_trace_record(
                episode_dir=episode_dir,
                mode=mode,
                accepted=bool(record and meta),
                stage="run",
                error=episode_error,
            )

        self._active_episode_context = {}
        self._active_call_context = {}
        self._episode_llm_calls = []

        return {
            "episode_dir": episode_dir,
            "mode": mode,
            "record": record,
            "meta": meta,
            "error": episode_error,
            "trace_record": trace_record,
            "duration_seconds": round(max(0.0, time.perf_counter() - started_at), 6),
        }

    async def run(
        self,
        input_dir: str,
        output_file: str,
        meta_file: str,
        limit: int = 0,
        input_mode: str = InputMode.AUTO.value,
    ):
        episodes = self._discover_episodes(input_dir, input_mode)

        if limit > 0:
            episodes = episodes[:limit]

        logger.info(
            "Found %d episodes to process (mode=%s, limit=%d).",
            len(episodes),
            input_mode,
            limit,
        )
        logger.info(
            "Synthesis settings: problem_loops=%d, trajectory_loops=%d, heuristic_fallback=%s, min_step_coverage=%.2f, skip_invalid_structure=%s, reject_failure_only_tools=%s, max_tool_failure_rate=%.2f",
            self.max_problem_refine_loops,
            self.max_trajectory_refine_loops,
            self.enable_heuristic_fallback,
            self.min_step_coverage_ratio,
            self.skip_invalid_structure,
            self.reject_failure_only_tools,
            self.max_tool_failure_rate,
        )
        logger.info(
            "Quality settings: gate_enabled=%s, policy=%s, fallback_for_training=%s, fallback_min_steps=%d, score_enabled=%s, min_high=%.2f, min_acceptable=%.2f",
            self.quality_gate_enabled,
            self.quality_policy,
            self.fallback_for_training,
            self.fallback_min_tool_steps,
            self.quality_score_enabled,
            self.min_quality_score_high,
            self.min_quality_score_acceptable,
        )
        run_started_at = datetime.now(timezone.utc)
        run_perf_start = time.perf_counter()

        valid_records = self._load_json_list(output_file)
        meta_records = self._load_json_list(meta_file)
        fallback_output_file = ""
        fallback_records: List[Dict[str, Any]] = []
        if self.quality_gate_enabled:
            fallback_output_file = self._resolve_fallback_output_path(output_file)
            fallback_records = self._load_json_list(fallback_output_file)
            logger.info("Quality fallback output: %s", fallback_output_file)
        llm_io_file = ""
        llm_io_records: List[Dict[str, Any]] = []
        if self.save_llm_io:
            llm_io_file = self._resolve_llm_io_path(output_file)
            llm_io_records = self._load_json_list(llm_io_file)
            logger.info("LLM trace output: %s", llm_io_file)

        accepted_count = 0
        quality_filtered_count = 0
        rejected_count = 0
        error_count = 0
        dedup_rejected_count = 0

        processed_episode_dirs = {
            m.get("episode_dir")
            for m in meta_records
            if isinstance(m, dict)
            and m.get("episode_dir")
            and bool(m.get("accepted", True))
        }

        # Load dedup state for resume support
        if self._dedup:
            output_dir = os.path.dirname(os.path.abspath(output_file))
            self._dedup.load_state(output_dir)
            # Seed dedup with already-accepted records (skip stats update to avoid double-counting)
            for existing_record in valid_records:
                # Register in dedup state without incrementing stats
                if hasattr(self._dedup, '_register_without_stats'):
                    self._dedup._register_without_stats(existing_record, {})
                else:
                    # Fallback: call should_keep but stats will be inflated
                    self._dedup.should_keep(existing_record, {})

        stage1_accept_counter: Counter[str] = Counter()
        stage2_accept_counter: Counter[str] = Counter()
        rejection_stage_counter: Counter[str] = Counter()
        rejection_reason_counter: Counter[str] = Counter()
        problem_failure_reason_counter: Counter[str] = Counter()
        trajectory_failure_reason_counter: Counter[str] = Counter()
        difficulty_counter_all: Counter[str] = Counter()
        difficulty_counter_accepted: Counter[str] = Counter()
        quality_tier_counter_all: Counter[str] = Counter()
        quality_tier_counter_training: Counter[str] = Counter()

        episode_durations: List[float] = []
        fallback_used_count = 0
        attempts_problem_total = 0
        attempts_traj_total = 0
        attempts_counted = 0
        strict_both_pass_count = 0

        llm_call_total = 0
        token_prompt_total = 0
        token_completion_total = 0
        token_total = 0

        pending_items: List[Dict[str, str]] = []
        pre_screened_count = 0
        for item in episodes:
            episode_dir = item["episode_dir"]
            if episode_dir in processed_episode_dirs:
                logger.info("Skipping already-processed episode: %s", episode_dir)
                continue

            # ---- Pre-screening ----
            if self.pre_screening_enabled:
                passed, reason, screen_meta = self._pre_screen_episode(episode_dir)
                if not passed:
                    pre_screened_count += 1
                    reject_meta = {
                        "id": str(uuid.uuid4()),
                        "episode_dir": episode_dir,
                        "source_mode": item.get("mode", "unknown"),
                        "accepted": False,
                        "selected_for_training": False,
                        "rejected_stage": "pre_screen",
                        "rejected_reason": reason,
                        "quality_tier": "reject",
                        "quality_score": 0.0,
                        "hard_judge_pass": False,
                        "soft_judge_pass": False,
                        "soft_judge_issues": [],
                        "problem_accept_mode": "unaccepted",
                        "trajectory_accept_mode": "unaccepted",
                        "problem_refine_attempts": 0,
                        "trajectory_refine_attempts": 0,
                        "problem_last_failure_reason": "N/A",
                        "trajectory_last_failure_reason": reason,
                        "fallback_used": False,
                        **screen_meta,
                    }
                    meta_records.append(reject_meta)
                    self._save_json_atomic(meta_file, meta_records)
                    processed_episode_dirs.add(episode_dir)
                    rejection_stage_counter["pre_screen"] += 1
                    rejection_reason_counter[reason] += 1
                    rejected_count += 1
                    logger.info(
                        "Episode %s PRE_SCREEN_REJECTED (%s): %s",
                        episode_dir,
                        item.get("mode", "?"),
                        reason,
                    )
                    continue
            # ---- End pre-screening ----

            pending_items.append(item)

        if pre_screened_count > 0:
            logger.info(
                "Pre-screening rejected %d episode(s); %d pending after pre-screen.",
                pre_screened_count,
                len(pending_items),
            )

        # Batch output save: meta_file is always atomic (resume safety),
        # but output_file (training data) is flushed every N accepted episodes.
        _batch_save_counter: int = 0
        _batch_flush_interval: int = 20

        def _flush_batch() -> None:
            if valid_records:
                self._save_json_atomic(output_file, valid_records)
            if fallback_output_file and fallback_records:
                self._save_json_atomic(fallback_output_file, fallback_records)

        def _maybe_flush_batch() -> None:
            nonlocal _batch_save_counter
            if _batch_save_counter >= _batch_flush_interval:
                _flush_batch()
                _batch_save_counter = 0

        def _consume_result(result: Dict[str, Any]) -> None:
            nonlocal _batch_save_counter
            nonlocal accepted_count
            nonlocal quality_filtered_count
            nonlocal rejected_count
            nonlocal error_count
            nonlocal dedup_rejected_count
            nonlocal fallback_used_count
            nonlocal attempts_problem_total
            nonlocal attempts_traj_total
            nonlocal attempts_counted
            nonlocal strict_both_pass_count
            nonlocal llm_call_total
            nonlocal token_prompt_total
            nonlocal token_completion_total
            nonlocal token_total
            nonlocal difficulty_counter_all
            nonlocal difficulty_counter_accepted
            nonlocal quality_tier_counter_all
            nonlocal quality_tier_counter_training

            episode_dir = result["episode_dir"]
            mode = result["mode"]
            record = result.get("record")
            meta = result.get("meta") or {}
            episode_error = str(result.get("error", "") or "")
            trace_record = result.get("trace_record")
            episode_duration = float(result.get("duration_seconds", 0.0) or 0.0)
            episode_durations.append(episode_duration)

            if trace_record:
                calls = trace_record.get("llm_calls") or []
                llm_call_total += len(calls)
                for call in calls:
                    usage = call.get("usage") or {}
                    token_prompt_total += int(usage.get("prompt_tokens", 0) or 0)
                    token_completion_total += int(usage.get("completion_tokens", 0) or 0)
                    token_total += int(usage.get("total_tokens", 0) or 0)

            if not isinstance(meta, dict):
                meta = {}

            if meta:
                meta["mode"] = mode
                meta["episode_duration_seconds"] = round(episode_duration, 6)
                if trace_record:
                    meta["llm_calls_count"] = len(trace_record.get("llm_calls") or [])
                diff_steps = int(
                    meta.get("difficulty_tool_steps", meta.get("tool_steps", 0)) or 0
                )
                if "difficulty_level" not in meta or "difficulty_rank" not in meta:
                    meta.update(self._difficulty_fields(diff_steps))
                if "selected_for_training" not in meta:
                    meta["selected_for_training"] = bool(meta.get("accepted", False))
                meta.setdefault("quality_tier", "reject")
                meta.setdefault("quality_score", 0.0)
                meta.setdefault("hard_judge_pass", False)
                meta.setdefault("soft_judge_pass", False)
                meta.setdefault("soft_judge_issues", [])

            if episode_error:
                error_count += 1
                if not meta:
                    meta = {
                        "id": str(uuid.uuid4()),
                        "episode_dir": episode_dir,
                        "source_mode": mode,
                        "accepted": False,
                        "selected_for_training": False,
                        "quality_tier": "reject",
                        "quality_score": 0.0,
                        "hard_judge_pass": False,
                        "soft_judge_pass": False,
                        "soft_judge_issues": [],
                    }
                if "difficulty_level" not in meta or "difficulty_rank" not in meta:
                    meta.update(
                        self._difficulty_fields(
                            int(meta.get("difficulty_tool_steps", 0) or 0)
                        )
                    )
                meta["rejected_stage"] = meta.get("rejected_stage") or "runtime_error"
                meta["rejected_reason"] = meta.get("rejected_reason") or episode_error
                meta["runtime_error"] = episode_error
                meta = self._sanitize_content(meta, episode_dir)
                meta["episode_dir"] = episode_dir  # preserve original for resume matching
                rejection_stage_counter[str(meta.get("rejected_stage") or "runtime_error")] += 1
                rejection_reason_counter[str(meta.get("rejected_reason") or episode_error)] += 1
                meta_records.append(meta)
                self._save_json_atomic(meta_file, meta_records)
            elif record and meta and bool(meta.get("accepted", True)):
                record = self._sanitize_content(record, episode_dir)
                meta = self._sanitize_content(meta, episode_dir)
                meta["episode_dir"] = episode_dir  # preserve original for resume matching

                selected_for_training = bool(meta.get("selected_for_training", True))
                if not selected_for_training:
                    fallback_records.append(record)
                    meta_records.append(meta)
                    processed_episode_dirs.add(episode_dir)
                    quality_filtered_count += 1
                    logger.info(
                        "Episode %s QUALITY-FILTERED (%s): tier=%s score=%.2f",
                        episode_dir,
                        mode,
                        str(meta.get("quality_tier", "unknown")),
                        float(meta.get("quality_score", 0.0) or 0.0),
                    )
                    if fallback_output_file:
                        _batch_save_counter += 1
                        _maybe_flush_batch()
                    self._save_json_atomic(meta_file, meta_records)
                else:
                    # --- Dataset-level dedup check ---
                    if self._dedup:
                        dedup_decision = self._dedup.should_keep(record, meta)
                        if not dedup_decision.should_keep:
                            dedup_rejected_count += 1
                            meta["accepted"] = False
                            meta["selected_for_training"] = False
                            meta["rejected_stage"] = "dedup"
                            meta["rejected_reason"] = dedup_decision.reason
                            if dedup_decision.similarity_score is not None:
                                meta["dedup_similarity"] = round(
                                    dedup_decision.similarity_score, 4
                                )
                            meta_records.append(meta)
                            self._save_json_atomic(meta_file, meta_records)
                            logger.info(
                                "Episode %s DEDUP-REJECTED (%s): %s",
                                episode_dir,
                                mode,
                                dedup_decision.reason,
                            )
                            rejected_count += 1
                        else:
                            valid_records.append(record)
                            meta_records.append(meta)
                            processed_episode_dirs.add(episode_dir)
                            accepted_count += 1
                            logger.info("Episode %s PASSED (%s).", episode_dir, mode)
                            _batch_save_counter += 1
                            _maybe_flush_batch()
                            self._save_json_atomic(meta_file, meta_records)
                    else:
                        valid_records.append(record)
                        meta_records.append(meta)
                        processed_episode_dirs.add(episode_dir)
                        accepted_count += 1
                        logger.info("Episode %s PASSED (%s).", episode_dir, mode)

                        _batch_save_counter += 1
                        _maybe_flush_batch()
                        self._save_json_atomic(meta_file, meta_records)
            else:
                rejected_count += 1
                if not meta:
                    meta = {
                        "id": str(uuid.uuid4()),
                        "episode_dir": episode_dir,
                        "source_mode": mode,
                        "accepted": False,
                        "rejected_stage": "unknown",
                        "rejected_reason": "episode rejected without diagnostic meta",
                        "selected_for_training": False,
                        "quality_tier": "reject",
                        "quality_score": 0.0,
                        "hard_judge_pass": False,
                        "soft_judge_pass": False,
                        "soft_judge_issues": [],
                    }
                if "difficulty_level" not in meta or "difficulty_rank" not in meta:
                    meta.update(
                        self._difficulty_fields(
                            int(meta.get("difficulty_tool_steps", 0) or 0)
                        )
                    )
                meta = self._sanitize_content(meta, episode_dir)
                meta["episode_dir"] = episode_dir  # preserve original for resume matching
                meta_records.append(meta)
                self._save_json_atomic(meta_file, meta_records)
                logger.info("Episode %s REJECTED (%s).", episode_dir, mode)

            if meta:
                meta = self._sanitize_content(meta, episode_dir)
                stage1_mode = str(meta.get("problem_accept_mode", "") or "unknown")
                stage2_mode = str(meta.get("trajectory_accept_mode", "") or "unknown")
                stage1_accept_counter[stage1_mode] += 1
                stage2_accept_counter[stage2_mode] += 1
                difficulty_level = str(meta.get("difficulty_level", "unknown") or "unknown")
                difficulty_counter_all[difficulty_level] += 1
                if bool(meta.get("accepted", False)):
                    difficulty_counter_accepted[difficulty_level] += 1
                quality_tier = str(meta.get("quality_tier", "unknown") or "unknown")
                quality_tier_counter_all[quality_tier] += 1
                if bool(meta.get("selected_for_training", False)):
                    quality_tier_counter_training[quality_tier] += 1

                if bool(meta.get("fallback_used", False)):
                    fallback_used_count += 1

                p_attempts = int(meta.get("problem_refine_attempts", 0) or 0)
                t_attempts = int(meta.get("trajectory_refine_attempts", 0) or 0)
                if p_attempts > 0 or t_attempts > 0:
                    attempts_problem_total += p_attempts
                    attempts_traj_total += t_attempts
                    attempts_counted += 1

                if stage1_mode == "judge_pass" and stage2_mode in {
                    "primary_judge_pass",
                    "dual_judge_pass",
                }:
                    strict_both_pass_count += 1

                p_fail_reason = str(meta.get("problem_last_failure_reason", "") or "").strip()
                if p_fail_reason and p_fail_reason.upper() != "N/A":
                    problem_failure_reason_counter[p_fail_reason] += 1
                t_fail_reason = str(meta.get("trajectory_last_failure_reason", "") or "").strip()
                if t_fail_reason and t_fail_reason.upper() != "N/A":
                    trajectory_failure_reason_counter[t_fail_reason] += 1

                rejected_stage = str(meta.get("rejected_stage", "") or "").strip()
                if rejected_stage:
                    rejection_stage_counter[rejected_stage] += 1
                rejected_reason = str(meta.get("rejected_reason", "") or "").strip()
                if rejected_reason:
                    rejection_reason_counter[rejected_reason] += 1

            if self.save_llm_io and llm_io_file and trace_record:
                llm_io_records.append(trace_record)
                self._save_json_atomic(llm_io_file, llm_io_records)

        if not pending_items:
            logger.info("No pending episodes after skipping already-processed entries.")
        elif self.num_workers <= 1 or len(pending_items) == 1:
            for item in pending_items:
                result = await self._process_episode_item(item)
                _consume_result(result)
        else:
            worker_count = min(self.num_workers, len(pending_items))
            logger.info(
                "Parallel synthesis enabled: workers=%d, pending=%d",
                worker_count,
                len(pending_items),
            )

            work_queue: "asyncio.Queue[Optional[Dict[str, str]]]" = asyncio.Queue()
            result_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

            for item in pending_items:
                work_queue.put_nowait(item)
            for _ in range(worker_count):
                work_queue.put_nowait(None)

            async def _worker_loop(worker_id: int) -> None:
                worker_pipeline = DataSynthesisPipeline(self.config_path)
                while True:
                    item = await work_queue.get()
                    try:
                        if item is None:
                            return
                        episode_dir = item.get("episode_dir", "???")
                        # ---- Per-episode timeout ----
                        if self.episode_timeout_seconds > 0:
                            try:
                                result = await asyncio.wait_for(
                                    worker_pipeline._process_episode_item(item),
                                    timeout=self.episode_timeout_seconds,
                                )
                            except asyncio.TimeoutError:
                                logger.warning(
                                    "Episode TIMEOUT worker-%d (%ds): %s",
                                    worker_id,
                                    self.episode_timeout_seconds,
                                    episode_dir,
                                )
                                await result_queue.put({
                                    "episode_dir": episode_dir,
                                    "mode": item.get("mode", "unknown"),
                                    "record": None,
                                    "meta": {
                                        "id": str(uuid.uuid4()),
                                        "source_mode": item.get("mode", "unknown"),
                                        "accepted": False,
                                        "selected_for_training": False,
                                        "rejected_stage": "episode_timeout",
                                        "rejected_reason": (
                                            f"episode exceeded {self.episode_timeout_seconds}s "
                                            f"timeout"
                                        ),
                                        "quality_tier": "reject",
                                        "quality_score": 0.0,
                                        "hard_judge_pass": False,
                                        "soft_judge_pass": False,
                                        "soft_judge_issues": [],
                                        "problem_accept_mode": "unaccepted",
                                        "trajectory_accept_mode": "unaccepted",
                                        "problem_refine_attempts": 0,
                                        "trajectory_refine_attempts": 0,
                                        "problem_last_failure_reason": "N/A",
                                        "trajectory_last_failure_reason": "episode timeout",
                                        "fallback_used": False,
                                        "episode_dir": episode_dir,
                                        "duration_seconds": float(self.episode_timeout_seconds),
                                    },
                                    "error": "",
                                    "trace_record": None,
                                    "duration_seconds": float(self.episode_timeout_seconds),
                                })
                            else:
                                await result_queue.put(result)
                        else:
                            # No per-episode timeout (backward compatible)
                            result = await worker_pipeline._process_episode_item(item)
                            await result_queue.put(result)
                        # ---- End per-episode timeout ----
                    except Exception as worker_exc:
                        logger.error(
                            "Worker-%d crashed on %s: %s",
                            worker_id,
                            item.get("episode_dir", "?") if item else "?",
                            worker_exc,
                        )
                        await result_queue.put({
                            "episode_dir": item.get("episode_dir", "???") if isinstance(item, dict) else "???",
                            "mode": item.get("mode", "unknown") if isinstance(item, dict) else "unknown",
                            "result": None,
                            "record": None,
                            "meta": {
                                "accepted": False,
                                "rejected_stage": "worker_crash",
                                "rejected_reason": str(worker_exc)[:200],
                                "selected_for_training": False,
                                "quality_tier": "reject",
                                "quality_score": 0.0,
                                "hard_judge_pass": False,
                                "soft_judge_pass": False,
                                "soft_judge_issues": [],
                            },
                            "error": str(worker_exc)[:500],
                            "trace_record": None,
                            "duration_seconds": 0.0,
                        })
                    finally:
                        work_queue.task_done()

            worker_tasks = [
                asyncio.create_task(_worker_loop(i))
                for i in range(worker_count)
            ]

            expected_results = len(pending_items)
            received = 0

            # Simple blocking consume loop — no global timeout.
            # Individual episode timeouts are handled inside workers.
            while received < expected_results:
                result = await result_queue.get()
                _consume_result(result)
                received += 1

            # Workers exit naturally via sentinel None when queue is exhausted.
            # No task cancellation needed.

        # Final batch flush — ensure all remaining output is saved
        _flush_batch()

        attempted = accepted_count + quality_filtered_count + rejected_count + error_count
        processed = accepted_count + quality_filtered_count + rejected_count
        pass_rate = (accepted_count / attempted * 100.0) if attempted > 0 else 0.0
        strict_stage1_pass_rate = (
            stage1_accept_counter.get("judge_pass", 0) / processed * 100.0
            if processed > 0
            else 0.0
        )
        strict_stage2_pass_rate = (
            (
                stage2_accept_counter.get("primary_judge_pass", 0)
                + stage2_accept_counter.get("dual_judge_pass", 0)
            )
            / processed
            * 100.0
            if processed > 0
            else 0.0
        )
        strict_both_pass_rate = (
            strict_both_pass_count / processed * 100.0 if processed > 0 else 0.0
        )
        fallback_used_rate = (
            fallback_used_count / processed * 100.0 if processed > 0 else 0.0
        )
        quality_filtered_rate = (
            quality_filtered_count / attempted * 100.0 if attempted > 0 else 0.0
        )
        avg_problem_attempts = (
            attempts_problem_total / attempts_counted if attempts_counted > 0 else 0.0
        )
        avg_trajectory_attempts = (
            attempts_traj_total / attempts_counted if attempts_counted > 0 else 0.0
        )
        duration_seconds = max(0.0, time.perf_counter() - run_perf_start)
        avg_episode_seconds = (
            sum(episode_durations) / len(episode_durations) if episode_durations else 0.0
        )
        llm_calls_per_episode = (
            llm_call_total / processed if processed > 0 else 0.0
        )

        def _top_counter_rows(counter: Counter[str], topn: int = 10) -> List[Dict[str, Any]]:
            return [
                {"reason": reason, "count": count}
                for reason, count in counter.most_common(topn)
            ]

        run_summary_record = {
            "record_type": "run_summary",
            "id": str(uuid.uuid4()),
            "timestamp_start": run_started_at.isoformat(),
            "timestamp_end": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration_seconds, 6),
            "input_mode": input_mode,
            "limit": limit,
            "num_workers": self.num_workers,
            "enable_heuristic_fallback": self.enable_heuristic_fallback,
            "skip_invalid_structure": self.skip_invalid_structure,
            "reject_failure_only_tools": self.reject_failure_only_tools,
            "max_tool_failure_rate": self.max_tool_failure_rate,
            "quality_gate_enabled": self.quality_gate_enabled,
            "quality_policy": self.quality_policy,
            "fallback_for_training": self.fallback_for_training,
            "quality_score_enabled": self.quality_score_enabled,
            "quality_score_thresholds": {
                "high": self.min_quality_score_high,
                "acceptable": self.min_quality_score_acceptable,
            },
            "attempted": attempted,
            "processed": processed,
            "accepted": accepted_count,
            "quality_filtered": quality_filtered_count,
            "rejected": rejected_count,
            "errors": error_count,
            "pass_rate_percent": round(pass_rate, 4),
            "quality_filtered_rate_percent": round(quality_filtered_rate, 4),
            "strict_stage1_pass_rate_percent": round(strict_stage1_pass_rate, 4),
            "strict_stage2_pass_rate_percent": round(strict_stage2_pass_rate, 4),
            "strict_both_pass_rate_percent": round(strict_both_pass_rate, 4),
            "fallback_used_count": fallback_used_count,
            "fallback_used_rate_percent": round(fallback_used_rate, 4),
            "avg_problem_refine_attempts": round(avg_problem_attempts, 4),
            "avg_trajectory_refine_attempts": round(avg_trajectory_attempts, 4),
            "avg_episode_seconds": round(avg_episode_seconds, 6),
            "llm_call_total": llm_call_total,
            "llm_calls_per_processed_episode": round(llm_calls_per_episode, 4),
            "token_usage": {
                "prompt_tokens": token_prompt_total,
                "completion_tokens": token_completion_total,
                "total_tokens": token_total,
            },
            "stage_accept_modes": {
                "problem_accept_mode": dict(stage1_accept_counter),
                "trajectory_accept_mode": dict(stage2_accept_counter),
            },
            "rejection_stages": dict(rejection_stage_counter),
            "difficulty_distribution_all": dict(difficulty_counter_all),
            "difficulty_distribution_accepted": dict(difficulty_counter_accepted),
            "rejection_reasons_top10": _top_counter_rows(rejection_reason_counter, topn=10),
            "problem_failure_reasons_top10": _top_counter_rows(
                problem_failure_reason_counter, topn=10
            ),
            "trajectory_failure_reasons_top10": _top_counter_rows(
                trajectory_failure_reason_counter, topn=10
            ),
        }
        if self.quality_shadow_report:
            run_summary_record["quality_distribution_all"] = dict(quality_tier_counter_all)
            run_summary_record["quality_distribution_training"] = dict(
                quality_tier_counter_training
            )

        # Add dedup stats to summary if enabled
        if self._dedup:
            run_summary_record["dedup_stats"] = self._dedup.get_stats()
            run_summary_record["dedup_rejected"] = dedup_rejected_count

        meta_records.append(run_summary_record)
        self._save_json_atomic(meta_file, meta_records)

        logger.info(
            "Run summary: attempted=%d, accepted=%d, quality_filtered=%d, rejected=%d, errors=%d, pass_rate=%.1f%%",
            attempted,
            accepted_count,
            quality_filtered_count,
            rejected_count,
            error_count,
            pass_rate,
        )
        logger.info(
            "Quality summary: strict_stage1=%.1f%% strict_stage2=%.1f%% strict_both=%.1f%% fallback_used=%.1f%%",
            strict_stage1_pass_rate,
            strict_stage2_pass_rate,
            strict_both_pass_rate,
            fallback_used_rate,
        )
        if self.quality_shadow_report:
            logger.info(
                "Quality shadow: policy=%s gate=%s dist_all=%s dist_training=%s",
                self.quality_policy,
                self.quality_gate_enabled,
                dict(quality_tier_counter_all),
                dict(quality_tier_counter_training),
            )
        logger.info(
            "Efficiency summary: duration=%.1fs avg_episode=%.1fs llm_calls=%d tokens=%d",
            duration_seconds,
            avg_episode_seconds,
            llm_call_total,
            token_total,
        )
        if self._dedup:
            dedup_stats = self._dedup.get_stats()
            logger.info(
                "Dedup summary: mode=%s, checked=%d, kept=%d, rejected_hash=%d, "
                "rejected_semantic=%d, rejected_max_variants=%d, dedup_rate=%.1f%%",
                dedup_stats.get("mode", "?"),
                dedup_stats.get("total_checked", 0),
                dedup_stats.get("kept", 0),
                dedup_stats.get("rejected_hash", 0),
                dedup_stats.get("rejected_semantic", 0),
                dedup_stats.get("rejected_max_variants", 0),
                dedup_stats.get("dedup_rate", 0.0) * 100,
            )
            # Persist dedup state for resume
            output_dir = os.path.dirname(os.path.abspath(output_file))
            self._dedup.save_state(output_dir)

        logger.info(
            "Final: Saved %d synthesized episode records to %s",
            len(valid_records),
            output_file,
        )
        if fallback_output_file:
            logger.info(
                "Final: Saved %d quality-filtered/fallback records to %s",
                len(fallback_records),
                fallback_output_file,
            )
        if self.save_llm_io and llm_io_file:
            logger.info(
                "Final: Saved %d LLM trace episode records to %s",
                len(llm_io_records),
                llm_io_file,
            )

    async def process_episode(
        self, episode_dir: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        with open(os.path.join(episode_dir, "problem.json"), "r", encoding="utf-8") as f:
            problem_data = json.load(f)
        with open(os.path.join(episode_dir, "trajectory.json"), "r", encoding="utf-8") as f:
            traj_data = json.load(f)

        if self.skip_invalid_structure:
            ok, reason, stats = self._validate_trajectory_structure(traj_data)
            if not ok:
                logger.warning(
                    "Skipping %s due to trajectory structural mismatch: %s",
                    episode_dir,
                    reason,
                )
                return (
                    None,
                    self._build_structure_rejection_meta(
                        source_mode=InputMode.SYNTHESIZED.value,
                        episode_dir=episode_dir,
                        task_type=str(
                            problem_data.get("task_type", TaskType.MUTATION.value)
                        ),
                        mcp_server=str(
                            (problem_data.get("mcp_server") or "filesystem").lower()
                        ),
                        rejected_reason=reason,
                        structure_stats=stats,
                    ),
                )

        quality_ok, quality_reason, quality_stats = self._run_tool_quality_gate(traj_data)
        if not quality_ok:
            logger.warning(
                "Skipping %s due to trajectory quality gate: %s",
                episode_dir,
                quality_reason,
            )
            return (
                None,
                self._build_tool_quality_rejection_meta(
                    source_mode=InputMode.SYNTHESIZED.value,
                    episode_dir=episode_dir,
                    task_type=str(problem_data.get("task_type", TaskType.MUTATION.value)),
                    mcp_server=str((problem_data.get("mcp_server") or "filesystem").lower()),
                    rejected_reason=quality_reason,
                    quality_stats=quality_stats,
                ),
            )

        return await self._process_with_problem_and_trajectory(
            problem_data=problem_data,
            traj_data=traj_data,
            episode_dir=episode_dir,
            source_mode=InputMode.SYNTHESIZED.value,
        )

    async def process_raw_episode(
        self, episode_dir: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        raw_context_path = os.path.join(episode_dir, "raw_context.json")
        trajectory_path = os.path.join(episode_dir, "trajectory.json")

        with open(raw_context_path, "r", encoding="utf-8") as f:
            raw_context = json.load(f)
        with open(trajectory_path, "r", encoding="utf-8") as f:
            traj_data = json.load(f)

        if self.skip_invalid_structure:
            ok, reason, stats = self._validate_trajectory_structure(traj_data)
            if not ok:
                logger.warning(
                    "Skipping %s due to trajectory structural mismatch: %s",
                    episode_dir,
                    reason,
                )
                return (
                    None,
                    self._build_structure_rejection_meta(
                        source_mode=InputMode.RAW.value,
                        episode_dir=episode_dir,
                        task_type=str(
                            raw_context.get("task_type", TaskType.MUTATION.value)
                        ),
                        mcp_server=str(raw_context.get("mcp_server", "filesystem")),
                        rejected_reason=reason,
                        structure_stats=stats,
                    ),
                )

        quality_ok, quality_reason, quality_stats = self._run_tool_quality_gate(traj_data)
        if not quality_ok:
            logger.warning(
                "Skipping %s due to trajectory quality gate: %s",
                episode_dir,
                quality_reason,
            )
            return (
                None,
                self._build_tool_quality_rejection_meta(
                    source_mode=InputMode.RAW.value,
                    episode_dir=episode_dir,
                    task_type=str(raw_context.get("task_type", TaskType.MUTATION.value)),
                    mcp_server=str(raw_context.get("mcp_server", "filesystem")),
                    rejected_reason=quality_reason,
                    quality_stats=quality_stats,
                ),
            )

        self._set_call_context(stage="problem_synthesis", source_mode=InputMode.RAW.value)
        try:
            problem_data = await self._synthesize_problem_from_raw(raw_context, traj_data)
        finally:
            self._clear_call_context()
        if not problem_data:
            tool_steps = len(self._extract_tool_calls_for_rewrite(traj_data, traj_data.get("messages", [])))
            return (
                None,
                {
                    "id": str(uuid.uuid4()),
                    "source_mode": InputMode.RAW.value,
                    "episode_dir": episode_dir,
                    "accepted": False,
                    "task_type": raw_context.get("task_type", TaskType.MUTATION.value),
                    "mcp_server": raw_context.get("mcp_server", "filesystem"),
                    "rejected_stage": "problem_synthesis",
                    "rejected_reason": "problem synthesis returned empty output",
                    "problem_accept_mode": "unaccepted",
                    "trajectory_accept_mode": "unaccepted",
                    "problem_refine_attempts": 0,
                    "trajectory_refine_attempts": 0,
                    "problem_last_failure_reason": "problem synthesis returned empty output",
                    "trajectory_last_failure_reason": "N/A",
                    "fallback_used": False,
                    "quality_tier": "reject",
                    "quality_score": 0.0,
                    "hard_judge_pass": False,
                    "soft_judge_pass": False,
                    "soft_judge_issues": [],
                    "selected_for_training": False,
                    "quality_selection_reason": "problem_synthesis_failed",
                    "tool_steps": tool_steps,
                    **self._difficulty_fields(tool_steps),
                },
            )

        for key in (
            "anchor_usage",
            "tool_exposure",
            "world_context",
            "state_evidence",
            "tools_subset",
        ):
            if key in raw_context and key not in problem_data:
                problem_data[key] = raw_context[key]

        # Optional hindsight rewrite in offline synthesis stage.
        self._set_call_context(stage="hindsight_rewrite", source_mode=InputMode.RAW.value)
        try:
            traj_data = await self._maybe_rewrite_trajectory_from_raw(
                traj_data=traj_data,
                problem_data=problem_data,
                language=raw_context.get("language")
                or getattr(self.config.trajs2data, "language", "en"),
            )
        finally:
            self._clear_call_context()

        return await self._process_with_problem_and_trajectory(
            problem_data=problem_data,
            traj_data=traj_data,
            episode_dir=episode_dir,
            source_mode=InputMode.RAW.value,
        )

    async def _synthesize_problem_from_raw(
        self, raw_context: Dict[str, Any], traj_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        task_type = raw_context.get("task_type", TaskType.MUTATION.value)
        tools_subset = raw_context.get("tools_subset") or []
        init_ops = raw_context.get("init_ops") or []
        mcp_server = raw_context.get("mcp_server", "filesystem")
        root = raw_context.get("filesystem_root", "/workspace")
        language = raw_context.get("language") or getattr(
            self.config.trajs2data, "language", "en"
        )

        if not tools_subset:
            tool_names = []
            for tc in traj_data.get("tool_calls", []):
                name = tc.get("tool_name")
                if name and name not in tool_names:
                    tool_names.append(name)
            tools_subset = [{"name": n} for n in tool_names]

        if task_type == TaskType.RETRIEVAL.value:
            retrieval_spec = self._rebuild_retrieval_spec(raw_context.get("retrieval_spec"))
            if retrieval_spec is None:
                strict_trajectory = self._strict_trajectory_from_dict(traj_data)
                retrieval_spec = build_retrieval_spec(
                    strict_trajectory.tool_calls,
                    root,
                    language=language,
                )

            return await rewrite_retrieval_to_problem_json(
                retrieval_spec=retrieval_spec,
                tools_subset=tools_subset,
                init_ops=init_ops,
                mcp_server=mcp_server,
                maas_client=self.client,
                model_config=self.rewrite_model,
                root=root,
                language=language,
            )

        intent_spec = self._rebuild_intent_spec(raw_context.get("intent_spec"))
        if intent_spec is None:
            intent_spec = self._fallback_intent_spec(raw_context)

        return await rewrite_to_problem_json(
            intent_spec=intent_spec,
            tools_subset=tools_subset,
            init_ops=init_ops,
            mcp_server=mcp_server,
            maas_client=self.client,
            model_config=self.rewrite_model,
            root=root,
            language=language,
            self_questioning_config=getattr(self.config.trajs2data, "self_questioning", None),
            embedding_provider=None,
        )

    def _rebuild_intent_spec(self, data: Optional[Dict[str, Any]]) -> Optional[IntentSpec]:
        if not data or not isinstance(data, dict):
            return None

        changes = data.get("changes", {}) if isinstance(data.get("changes"), dict) else {}

        def _num(key: str, default: int = 0) -> int:
            value = data.get(key)
            if value is None:
                value = changes.get(key, default)
            try:
                return int(value)
            except Exception:
                return default

        category_raw = data.get("task_category", TaskCategory.MIXED.value)
        try:
            category = TaskCategory(category_raw)
        except Exception:
            category = TaskCategory.MIXED

        return IntentSpec(
            primary_action=data.get("primary_action", "modify_filesystem"),
            task_category=category,
            files_created=_num("files_created", _num("created_count", 0)),
            files_deleted=_num("files_deleted", _num("deleted_count", 0)),
            files_modified=_num("files_modified", _num("modified_count", 0)),
            files_moved=_num("files_moved", _num("moved_count", 0)),
            directories_created=_num("directories_created", 0),
            directories_deleted=_num("directories_deleted", 0),
            affected_directories=list(data.get("affected_directories", [])),
            file_types_involved=set(data.get("file_types_involved", [])),
            naming_patterns=list(data.get("naming_patterns", [])),
            tools_used=list(data.get("tools_used", [])),
            tool_call_count=_num("tool_call_count", 0),
            complexity_score=max(1, min(5, _num("complexity_score", 1))),
            sample_changes=list(data.get("sample_changes", [])),
        )

    def _fallback_intent_spec(self, raw_context: Dict[str, Any]) -> IntentSpec:
        diff_summary = raw_context.get("diff_summary", {})
        if not isinstance(diff_summary, dict):
            diff_summary = {}

        created = int(diff_summary.get("created", 0) or 0)
        deleted = int(diff_summary.get("deleted", 0) or 0)
        modified = int(diff_summary.get("modified", 0) or 0)
        moved = int(diff_summary.get("moved", 0) or 0)
        total = int(diff_summary.get("total", created + deleted + modified + moved) or 0)

        return IntentSpec(
            primary_action="modify_filesystem",
            task_category=TaskCategory.MIXED,
            files_created=created,
            files_deleted=deleted,
            files_modified=modified,
            files_moved=moved,
            tools_used=list(raw_context.get("tools_allowed", [])),
            tool_call_count=max(1, len(raw_context.get("tools_allowed", []))),
            complexity_score=max(1, min(5, total if total > 0 else 1)),
            sample_changes=[],
        )

    def _rebuild_retrieval_spec(
        self, data: Optional[Dict[str, Any]]
    ) -> Optional[RetrievalSpec]:
        if not data or not isinstance(data, dict):
            return None

        category_raw = data.get("task_category", TaskCategory.INFORMATION_RETRIEVAL.value)
        try:
            category = TaskCategory(category_raw)
        except Exception:
            category = TaskCategory.INFORMATION_RETRIEVAL

        return RetrievalSpec(
            query_focus=data.get("query_focus", "unknown"),
            task_category=category,
            evidence_tool=data.get("evidence_tool", ""),
            evidence_arguments=data.get("evidence_arguments", {}),
            evidence_snippet=data.get("evidence_snippet", ""),
            reference_answer=data.get("reference_answer", ""),
            answer_truncated=bool(data.get("answer_truncated", False)),
            tools_used=list(data.get("tools_used", [])),
            tool_call_count=int(data.get("tool_call_count", 0) or 0),
            tool_call_summaries=list(data.get("tool_call_summaries", [])),
            complexity_score=max(1, min(5, int(data.get("complexity_score", 1) or 1))),
        )

    def _strict_trajectory_from_dict(self, traj_data: Dict[str, Any]) -> StrictTrajectory:
        tool_calls = []
        for item in traj_data.get("tool_calls", []):
            tool_calls.append(
                ToolCallRecord(
                    tool_name=item.get("tool_name", item.get("name", "unknown")),
                    arguments=item.get("arguments", {}) or {},
                    result=item.get("result", "") or "",
                    success=bool(item.get("success", True)),
                    call_id=item.get("call_id", ""),
                    error_message=item.get("error_message"),
                )
            )

        status_raw = traj_data.get("status", EpisodeStatus.SUCCESS.value)
        try:
            status = EpisodeStatus(status_raw)
        except Exception:
            status = EpisodeStatus.SUCCESS

        return StrictTrajectory(
            messages=list(traj_data.get("messages", [])),
            tool_calls=tool_calls,
            tools_used=list(traj_data.get("tools_used", [])),
            num_steps=int(traj_data.get("num_steps", 0) or 0),
            num_successful_tool_calls=int(traj_data.get("num_successful_tool_calls", 0) or 0),
            target_n=int(traj_data.get("target_n", 0) or 0),
            status=status,
            abort_reason=traj_data.get("abort_reason"),
            execution_time=float(traj_data.get("execution_time", 0.0) or 0.0),
            model_name=traj_data.get("model_name"),
            token_usage=traj_data.get("token_usage") or {"prompt": 0, "completion": 0, "total": 0},
        )

    async def _maybe_rewrite_trajectory_from_raw(
        self,
        traj_data: Dict[str, Any],
        problem_data: Dict[str, Any],
        language: str,
    ) -> Dict[str, Any]:
        hindsight_cfg = getattr(self.config.trajs2data, "hindsight", None)
        if not (hindsight_cfg and hindsight_cfg.enabled and hindsight_cfg.rewrite_thoughts):
            return traj_data

        strict_trajectory = self._strict_trajectory_from_dict(traj_data)
        original = copy.deepcopy(traj_data)

        rewritten = await rewrite_trajectory_thoughts(
            trajectory=strict_trajectory,
            problem=problem_data,
            maas_client=self.client,
            model_config=self.rewrite_model,
            language=language,
        )

        rewritten_dict = rewritten.to_dict()
        rewritten_dict["original_trajectory"] = original
        return rewritten_dict

    def _anchor_tools_for_candidate_selection(
        self, problem_data: Dict[str, Any]
    ) -> List[str]:
        anchor_usage = problem_data.get("anchor_usage") or {}
        tool_exposure = problem_data.get("tool_exposure") or {}
        anchors: List[str] = []

        def _extend(values: Any) -> None:
            if isinstance(values, list):
                for value in values:
                    name = str(value or "").strip()
                    if name and name not in anchors:
                        anchors.append(name)

        if isinstance(anchor_usage, dict):
            _extend(anchor_usage.get("exposed_anchors"))
            _extend(anchor_usage.get("required_anchors"))
            final_prefix = anchor_usage.get("final_prefix")
            if isinstance(final_prefix, dict):
                _extend(final_prefix.get("successful_anchors"))
                _extend(final_prefix.get("attempted_anchors"))

        if isinstance(tool_exposure, dict):
            _extend(tool_exposure.get("anchor_tools"))
            _extend(tool_exposure.get("required_tools"))

        return anchors

    @staticmethod
    def _tools_used_for_candidate_selection(
        ordered_tool_calls: List[Dict[str, Any]]
    ) -> List[str]:
        successful: List[str] = []
        attempted: List[str] = []
        for tool_call in ordered_tool_calls:
            name = str(tool_call.get("tool_name", "") or "").strip()
            if not name:
                continue
            if name not in attempted:
                attempted.append(name)
            if bool(tool_call.get("success", True)) and name not in successful:
                successful.append(name)
        return successful or attempted

    async def _select_stage1_problem_candidate(
        self,
        *,
        problem_data: Dict[str, Any],
        ordered_tool_calls: List[Dict[str, Any]],
        fallback_problem_text: str,
        task_type: str = "mutation",
        trajectory_evidence: str = "",
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        candidates = extract_problem_candidates(problem_data)
        if not candidates:
            return fallback_problem_text, None

        if len(candidates) == 1:
            selected_problem = candidates[0] or fallback_problem_text
            if selected_problem:
                problem_data["problem"] = selected_problem
            return selected_problem, None

        self_questioning_cfg = getattr(self.config.trajs2data, "self_questioning", None)
        novelty_weight = float(getattr(self_questioning_cfg, "novelty_weight", 0.6) or 0.6)
        coverage_weight = float(getattr(self_questioning_cfg, "coverage_weight", 0.4) or 0.4)

        # Attempt LLM-based parallel candidate judging; fall back to rule-based on failure.
        llm_selection = await self._try_llm_candidate_selection(
            candidates=candidates,
            task_type=task_type,
            trajectory_evidence=trajectory_evidence,
        )
        if llm_selection is not None:
            selected_problem, selection_meta = llm_selection
            problem_data["problem"] = selected_problem
            problem_data["stage1_candidate_selection"] = selection_meta
            return selected_problem, selection_meta

        # Rule-based fallback
        selection = select_problem_candidate(
            candidates=candidates,
            tools_used=self._tools_used_for_candidate_selection(ordered_tool_calls),
            anchor_tools=self._anchor_tools_for_candidate_selection(problem_data),
            existing_problem_texts=[],
            novelty_weight=novelty_weight,
            coverage_weight=coverage_weight,
        )
        problem_data["problem"] = selection.selected_problem
        selection_meta = selection.to_dict()
        selection_meta["source"] = "stage1_rule_based_candidate_selection"
        selection_meta["novelty_weight"] = novelty_weight
        selection_meta["coverage_weight"] = coverage_weight
        problem_data["stage1_candidate_selection"] = selection_meta
        return selection.selected_problem, selection_meta

    async def _try_llm_candidate_selection(
        self,
        *,
        candidates: List[str],
        task_type: str,
        trajectory_evidence: str,
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Parallel LLM judge on all candidates, pick best by overall score.

        Returns None if LLM judging is unavailable or fails, so caller falls back to rules.
        """
        prompt_bundle = PromptLoader("filesystem").get_judge_prompt_bundle()
        judge_system = prompt_bundle.get("JUDGE_CANDIDATE_SYSTEM_PROMPT", "")
        judge_user_template = prompt_bundle.get("JUDGE_CANDIDATE_USER_TEMPLATE", "")
        if not judge_system or not judge_user_template:
            logger.info("Candidate judge prompts not available, skipping LLM selection")
            return None

        world_context_text = self._format_world_context_for_judge(problem_data={})
        evidence = trajectory_evidence or "No trajectory evidence available."
        evidence = evidence[:4096]  # Truncate to avoid blowing up context

        async def _judge_one(candidate: str) -> Optional[Dict[str, Any]]:
            user_prompt = judge_user_template.format(
                world_context=world_context_text,
                task_type=task_type,
                candidate=candidate,
                trajectory_evidence=evidence,
            )
            try:
                result = await self._call_judge_model(
                    system_prompt=judge_system,
                    user_prompt=user_prompt,
                )
                return result
            except Exception:
                logger.debug(
                    "LLM candidate judge failed for candidate: %.80s...", candidate
                )
                return None

        try:
            results = await asyncio.gather(
                *[_judge_one(c) for c in candidates[:5]],  # max 5 candidates
                return_exceptions=True,
            )
        except Exception:
            logger.warning("LLM candidate selection gather failed, falling back to rules")
            return None

        # Score and select best
        best_idx = -1
        best_score = -1.0
        all_scores: List[Dict[str, Any]] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception) or not isinstance(result, dict):
                all_scores.append({"error": str(result) if isinstance(result, Exception) else "no_result"})
                continue
            overall = float(result.get("overall", 0) or 0)
            all_scores.append({
                "index": idx,
                "candidate_preview": candidates[idx][:120] if idx < len(candidates) else "",
                "consistency": result.get("consistency"),
                "specificity": result.get("specificity"),
                "naturalness": result.get("naturalness"),
                "overall": overall,
                "reason": result.get("reason", ""),
            })
            if overall > best_score:
                best_score = overall
                best_idx = idx

        if best_idx < 0 or best_score < 0.0:
            logger.info("No valid LLM candidate scores, falling back to rules")
            return None

        selected_problem = candidates[best_idx]
        selection_meta = {
            "source": "stage1_llm_parallel_candidate_selection",
            "selected_index": best_idx,
            "selected_score": best_score,
            "num_candidates_judged": len(results),
            "all_scores": all_scores,
        }
        return selected_problem, selection_meta

    async def _process_with_problem_and_trajectory(
        self,
        problem_data: Dict[str, Any],
        traj_data: Dict[str, Any],
        episode_dir: str,
        source_mode: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        problem_text = (problem_data.get("problem", "") or "").strip()
        if not problem_text:
            problem_text = (problem_data.get("collection_task_objective", "") or "").strip()
        task_type = str(problem_data.get("task_type", TaskType.MUTATION.value))
        mcp_server = (problem_data.get("mcp_server") or "filesystem").lower()
        meta_id = str(uuid.uuid4())
        current_messages = traj_data.get("messages", [])
        ordered_tool_calls = self._extract_tool_calls_for_rewrite(traj_data, current_messages)
        expected_tool_steps = len(ordered_tool_calls)
        difficulty_fields = self._difficulty_fields(expected_tool_steps)
        problem_text, stage1_candidate_selection = await self._select_stage1_problem_candidate(
            problem_data=problem_data,
            ordered_tool_calls=ordered_tool_calls,
            fallback_problem_text=problem_text,
            task_type=task_type,
            trajectory_evidence=self._summarize_ordered_tool_call_evidence(ordered_tool_calls),
        )

        if not problem_text:
            logger.warning("Episode %s has empty problem text.", episode_dir)
            return (
                None,
                {
                    "id": meta_id,
                    "source_mode": source_mode,
                    "episode_dir": episode_dir,
                    "accepted": False,
                    "task_type": task_type,
                    "mcp_server": mcp_server,
                    "problem_refine_attempts": 0,
                    "trajectory_refine_attempts": 0,
                    "problem_accept_mode": "unaccepted",
                    "trajectory_accept_mode": "unaccepted",
                    "problem_last_failure_reason": "empty problem text",
                    "trajectory_last_failure_reason": "N/A",
                    "rejected_stage": "input_validation",
                    "rejected_reason": "empty problem text",
                    "fallback_used": False,
                    "quality_tier": "reject",
                    "quality_score": 0.0,
                    "hard_judge_pass": False,
                    "soft_judge_pass": False,
                    "soft_judge_issues": [],
                    "stage1_candidate_selection": stage1_candidate_selection,
                    "selected_for_training": False,
                    "quality_selection_reason": "input_validation_failed",
                    **difficulty_fields,
                },
            )
        reference_answer = str(problem_data.get("reference_answer", "") or "")

        original_traj = traj_data.get("original_trajectory", {}).get("messages", [])
        if not original_traj:
            original_candidate = traj_data.get("original_trajectory", [])
            if isinstance(original_candidate, list):
                original_traj = original_candidate
            else:
                original_traj = traj_data.get("messages", [])

        prompt_bundle = PromptLoader(mcp_server).get_judge_prompt_bundle()
        world_context_text = self._format_world_context_for_judge(problem_data)
        for key in list(prompt_bundle.keys()):
            if key.endswith("_USER_TEMPLATE") and prompt_bundle[key]:
                prompt_bundle[key] = prompt_bundle[key].replace(
                    "{world_context}", world_context_text
                )
        action_summary = self._summarize_actions(original_traj)
        tool_call_evidence_summary = self._summarize_ordered_tool_call_evidence(
            ordered_tool_calls
        )
        if self._is_empty_action_summary(action_summary):
            action_summary = tool_call_evidence_summary
        elif tool_call_evidence_summary:
            action_summary = (
                f"{action_summary}\n\nSupplemental normalized tool-call evidence:\n"
                f"{tool_call_evidence_summary}"
            )

        stage1_result = await self._run_stage1_problem_consistency(
            episode_dir=episode_dir,
            problem_text=problem_text,
            task_type=task_type,
            action_summary=action_summary,
            expected_tool_steps=expected_tool_steps,
            ordered_tool_calls=ordered_tool_calls,
            prompt_bundle=prompt_bundle,
            collection_task_type=task_type,
        )
        final_problem = stage1_result.final_problem
        consistent = stage1_result.consistent
        problem_attempts = stage1_result.attempts
        problem_accept_mode = stage1_result.accept_mode
        problem_last_failure_reason = stage1_result.last_failure_reason

        if not consistent:
            logger.info(
                "Episode %s rejected: problem synthesis not consistent after %d attempts.",
                episode_dir,
                problem_attempts,
            )
            return (
                None,
                {
                    "id": meta_id,
                    "source_mode": source_mode,
                    "original_problem": problem_text,
                    "final_problem": final_problem,
                    "episode_dir": episode_dir,
                    "complexity": problem_data.get("complexity_score"),
                    "task_type": task_type,
                    "mcp_server": mcp_server,
                    "accepted": False,
                    "rejected_stage": "stage1_problem_consistency",
                    "rejected_reason": problem_last_failure_reason,
                    "problem_refine_attempts": problem_attempts,
                    "trajectory_refine_attempts": 0,
                    "problem_accept_mode": problem_accept_mode,
                    "trajectory_accept_mode": "unaccepted",
                    "problem_last_failure_reason": problem_last_failure_reason,
                    "trajectory_last_failure_reason": "N/A",
                    "fallback_used": (problem_accept_mode != "judge_pass"),
                    "quality_tier": "reject",
                    "quality_score": 0.0,
                    "hard_judge_pass": False,
                    "soft_judge_pass": False,
                    "soft_judge_issues": [],
                    "stage1_candidate_selection": stage1_candidate_selection,
                    "selected_for_training": False,
                    "quality_selection_reason": "stage1_rejected",
                    "tool_steps": expected_tool_steps,
                    **difficulty_fields,
                },
            )

        stage2_result = await self._run_stage2_trajectory_rewrite(
            final_problem=final_problem,
            task_type=task_type,
            current_messages=current_messages,
            ordered_tool_calls=ordered_tool_calls,
            reference_answer=reference_answer,
            prompt_bundle=prompt_bundle,
        )
        realistic = stage2_result.realistic
        final_messages = stage2_result.final_messages
        trajectory_attempts = stage2_result.attempts
        trajectory_accept_mode = stage2_result.accept_mode
        trajectory_last_failure_reason = stage2_result.last_failure_reason
        quality_signal = self._compute_quality_signal(
            stage2_result, tool_steps=expected_tool_steps, mcp_server=mcp_server,
        )
        selected_for_training, quality_selection_reason = self._decide_training_selection(
            quality_tier=str(quality_signal.get("quality_tier", "reject")),
            quality_score=float(quality_signal.get("quality_score", 0.0) or 0.0),
            is_fallback_path=bool(quality_signal.get("is_fallback_path", False)),
            tool_steps=expected_tool_steps,
            mcp_server=mcp_server,
        )

        if not realistic:
            logger.info(
                "Episode %s rejected: trajectory rewrite not realistic after %d attempts.",
                episode_dir,
                trajectory_attempts,
            )
            return (
                None,
                {
                    "id": meta_id,
                    "source_mode": source_mode,
                    "original_problem": problem_text,
                    "final_problem": final_problem,
                    "episode_dir": episode_dir,
                    "complexity": problem_data.get("complexity_score"),
                    "task_type": task_type,
                    "mcp_server": mcp_server,
                    "accepted": False,
                    "rejected_stage": "stage2_trajectory_rewrite",
                    "rejected_reason": trajectory_last_failure_reason,
                    "problem_refine_attempts": problem_attempts,
                    "trajectory_refine_attempts": trajectory_attempts,
                    "problem_accept_mode": problem_accept_mode,
                    "trajectory_accept_mode": trajectory_accept_mode,
                    "problem_last_failure_reason": problem_last_failure_reason,
                    "trajectory_last_failure_reason": trajectory_last_failure_reason,
                    "fallback_used": (
                        problem_accept_mode != "judge_pass"
                        or trajectory_accept_mode
                        not in {"primary_judge_pass", "dual_judge_pass"}
                    ),
                    "quality_tier": quality_signal.get("quality_tier", "reject"),
                    "quality_score": quality_signal.get("quality_score", 0.0),
                    "hard_judge_pass": quality_signal.get("hard_judge_pass", False),
                    "soft_judge_pass": quality_signal.get("soft_judge_pass", False),
                    "soft_judge_issues": quality_signal.get("soft_judge_issues", []),
                    "stage1_candidate_selection": stage1_candidate_selection,
                    "selected_for_training": False,
                    "quality_selection_reason": "stage2_unrealistic",
                    "tool_steps": expected_tool_steps,
                    **difficulty_fields,
                },
            )

        # Review-friendly output (not direct SFT format)
        record = self._build_review_record(
            final_problem=final_problem,
            problem_data=problem_data,
            traj_data=traj_data,
            final_messages=final_messages,
            episode_dir=episode_dir,
            source_mode=source_mode,
            quality_tier=str(quality_signal.get("quality_tier", "reject")),
            quality_score=float(quality_signal.get("quality_score", 0.0) or 0.0),
            hard_judge_pass=bool(quality_signal.get("hard_judge_pass", False)),
            soft_judge_pass=bool(quality_signal.get("soft_judge_pass", False)),
            soft_judge_issues=list(quality_signal.get("soft_judge_issues", []) or []),
            selected_for_training=selected_for_training,
        )

        meta = {
            "id": meta_id,
            "source_mode": source_mode,
            "original_problem": problem_text,
            "final_problem": final_problem,
            "episode_dir": episode_dir,
            "complexity": problem_data.get("complexity_score"),
            "tool_calls": len([m for m in final_messages if m.get("tool_calls")]),
            "tool_steps": expected_tool_steps,
            "task_type": problem_data.get("task_type", TaskType.MUTATION.value),
            "mcp_server": problem_data.get("mcp_server", "filesystem"),
            "problem_refine_attempts": problem_attempts,
            "trajectory_refine_attempts": trajectory_attempts,
            "problem_accept_mode": problem_accept_mode,
            "trajectory_accept_mode": trajectory_accept_mode,
            "problem_last_failure_reason": problem_last_failure_reason,
            "trajectory_last_failure_reason": trajectory_last_failure_reason,
            "accepted": True,
            "rejected_stage": "",
            "rejected_reason": "",
            "fallback_used": (
                problem_accept_mode != "judge_pass"
                or trajectory_accept_mode
                not in {"primary_judge_pass", "dual_judge_pass"}
            ),
            "quality_tier": quality_signal.get("quality_tier", "reject"),
            "quality_score": quality_signal.get("quality_score", 0.0),
            "hard_judge_pass": quality_signal.get("hard_judge_pass", False),
            "soft_judge_pass": quality_signal.get("soft_judge_pass", False),
            "soft_judge_issues": quality_signal.get("soft_judge_issues", []),
            "stage1_candidate_selection": stage1_candidate_selection,
            "selected_for_training": selected_for_training,
            "quality_selection_reason": quality_selection_reason,
            **difficulty_fields,
        }

        return record, meta

    @staticmethod
    @staticmethod
    def _format_world_context_for_judge(problem_data: Dict[str, Any]) -> str:
        """Extract and format world_context from problem_data for judge prompts."""
        wc = problem_data.get("world_context")
        if not wc:
            return "No domain-specific world context available."
        if isinstance(wc, dict):
            parts = []
            for key, value in wc.items():
                if value:
                    text = str(value)
                    text = text.replace("{", "{{").replace("}", "}}")
                    parts.append(f"- {key}: {text}")
            return "\n".join(parts) if parts else "No domain-specific world context available."
        return str(wc).replace("{", "{{").replace("}", "}}")

    def _summarize_actions(self, messages: List[Dict]) -> str:
        if not messages:
            return "No observable trajectory actions were found."

        tool_outputs = [
            str(msg.get("content", ""))
            for msg in messages
            if msg.get("role") == "tool"
        ]
        output_idx = 0
        summary: List[str] = []
        step = 1

        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = fn.get("name", "unknown")
                args_raw = fn.get("arguments", {})
                args_preview = self._truncate_text(args_raw)
                if len(args_preview) > 180:
                    args_preview = f"{args_preview[:177]}..."

                result_text = ""
                if output_idx < len(tool_outputs):
                    result_text = tool_outputs[output_idx]
                    output_idx += 1
                result_preview = self._truncate_text(result_text)
                if len(result_preview) > 260:
                    result_preview = f"{result_preview[:257]}..."

                lowered_result = result_preview.lower()
                success = not any(
                    marker in lowered_result
                    for marker in (
                        "mcp error", "validation error", "traceback", "failed",
                        "tool execution error", "no active episode",
                    )
                )
                status = "ok" if success else "error"
                summary.append(
                    f"{step}. tool={name} args={args_preview} status={status} result={result_preview}"
                )
                step += 1

        if not summary:
            fallback = []
            for idx, output in enumerate(tool_outputs[:8], start=1):
                preview = self._truncate_text(output)
                if len(preview) > 260:
                    preview = f"{preview[:257]}..."
                fallback.append(f"{idx}. tool_result={preview}")
            if fallback:
                return "Observed tool outputs without explicit tool-call metadata:\n" + "\n".join(
                    fallback
                )
            return "No observable trajectory actions were found."

        return "Observed trajectory evidence:\n" + "\n".join(summary)

    @staticmethod
    def _is_empty_action_summary(summary: str) -> bool:
        text = (summary or "").strip().lower()
        return (not text) or ("no observable trajectory actions were found." in text)

    def _summarize_ordered_tool_call_evidence(
        self, tool_calls: List[Dict[str, Any]]
    ) -> str:
        if not tool_calls:
            return "No normalized tool-call evidence was found."

        lines: List[str] = []
        for idx, tc in enumerate(tool_calls[:60], start=1):
            tool_name = tc.get("tool_name", "unknown")
            args = tc.get("arguments", {}) or {}
            focus = self._extract_focus_hint(args)
            success = bool(tc.get("success", True))
            status = "ok" if success else "error"

            result_preview = self._truncate_text(tc.get("result", "") or "")
            result_preview = re.sub(r"\s+", " ", result_preview).strip()
            if len(result_preview) > 220:
                result_preview = f"{result_preview[:217]}..."

            line = f"{idx}. tool={tool_name}"
            if focus:
                line += f" {focus}"
            line += f" status={status}"
            if result_preview:
                line += f" result={result_preview}"
            lines.append(line)

        if len(tool_calls) > 60:
            lines.append(
                f"... ({len(tool_calls) - 60} additional tool-call steps omitted)"
            )

        return "Observed normalized tool-call evidence:\n" + "\n".join(lines)

    def _messages_to_text(self, messages: List[Dict]) -> str:
        text: List[str] = []
        step = 1
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            role_label = str(role).capitalize() or "Unknown"
            text.append(f"{role_label}:\n{content}")
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    args = tc.get("function", {}).get("arguments", {})
                    text.append(
                        f"ToolCall {step}: name={tc['function']['name']} args={self._truncate_text(args)}"
                    )
                    step += 1
        return "\n\n".join(text)

    def _extract_tool_calls_for_rewrite(
        self,
        traj_data: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        def _normalize_from_messages() -> List[Dict[str, Any]]:
            tool_results = []
            for msg in messages:
                if msg.get("role") == "tool":
                    tool_results.append(msg.get("content", ""))

            normalized_local: List[Dict[str, Any]] = []
            step_local = 1
            tool_result_idx = 0
            for msg in messages:
                for tc in msg.get("tool_calls", []) or []:
                    args_raw = tc.get("function", {}).get("arguments", {})
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except Exception:
                            args = {"raw_arguments": args_raw}
                    elif isinstance(args_raw, dict):
                        args = args_raw
                    else:
                        args = {}

                    result = (
                        tool_results[tool_result_idx]
                        if tool_result_idx < len(tool_results)
                        else ""
                    )
                    tool_result_idx += 1
                    result_text = str(result or "")
                    lowered_result = result_text.lower()
                    success = not any(
                        marker in lowered_result
                        for marker in (
                            "mcp error", "validation error", "traceback", "failed",
                            "tool execution error", "no active episode",
                        )
                    )
                    error_message = result_text if (not success and result_text) else None
                    normalized_local.append(
                        {
                            "step": step_local,
                            "tool_name": tc.get("function", {}).get("name", "unknown"),
                            "arguments": args,
                            "result": result,
                            "success": success,
                            "error_message": error_message,
                        }
                    )
                    step_local += 1

            return normalized_local

        message_normalized = _normalize_from_messages()
        raw_tool_calls = traj_data.get("tool_calls", [])
        if isinstance(raw_tool_calls, list) and raw_tool_calls:
            normalized = []
            for idx, tc in enumerate(raw_tool_calls, start=1):
                if not isinstance(tc, dict):
                    continue
                normalized.append(
                    {
                        "step": idx,
                        "tool_name": tc.get("tool_name", tc.get("name", "unknown")),
                        "arguments": tc.get("arguments", {}) or {},
                        "result": tc.get("result", "") or "",
                        "success": bool(tc.get("success", True)),
                        "error_message": tc.get("error_message"),
                    }
                )
            if normalized:
                if message_normalized and len(normalized) != len(message_normalized):
                    logger.warning(
                        "Tool-call count mismatch between trajectory.tool_calls (%d) and message-derived calls (%d); using message-derived sequence for rewrite/judge consistency.",
                        len(normalized),
                        len(message_normalized),
                    )
                    return message_normalized
                return normalized

        return message_normalized

    @staticmethod
    def _truncate_text(value: Any) -> str:
        if isinstance(value, str):
            text = value
        else:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except Exception:
                text = str(value)
        return text

    @staticmethod
    def _extract_result_summary(tc: Dict[str, Any]) -> str:
        """Extract a compact summary of the tool's actual output.

        Strips FastMCP wrapping to surface the real content the tool returned.
        """
        result = tc.get("result")
        if result is None:
            return ""
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                text = result
                if len(text) > 200:
                    text = f"{text[:197]}..."
                return text
        elif isinstance(result, dict):
            parsed = result
        else:
            text = str(result)
            if len(text) > 200:
                text = f"{text[:197]}..."
            return text

        # Try to unwrap FastMCP-style: {"content": [{"text": "..."}]}
        if isinstance(parsed, dict):
            content_list = parsed.get("content")
            if isinstance(content_list, list):
                texts = []
                for item in content_list:
                    if isinstance(item, dict) and "text" in item:
                        texts.append(str(item["text"]))
                if texts:
                    combined = " ".join(texts)
                    if len(combined) > 300:
                        combined = f"{combined[:297]}..."
                    return combined
            # Fallback: stringify the whole dict but limit length
            text = json.dumps(parsed, ensure_ascii=False)
            if len(text) > 200:
                text = f"{text[:197]}..."
            return text
        return ""

    def _build_tool_sequence_for_prompt(self, tool_calls: List[Dict[str, Any]]) -> str:
        rows: List[Dict[str, Any]] = []
        limit = self.rewrite_tool_sequence_max_steps
        selected = tool_calls[:limit]
        for tc in selected:
            args = tc.get("arguments", {})
            focus = self._extract_focus_hint(args)
            error_message = tc.get("error_message") or ""
            if not error_message and (not bool(tc.get("success", True))):
                error_message = self._truncate_text(tc.get("result", ""))
            error_message = self._truncate_text(error_message)
            if len(error_message) > 180:
                error_message = f"{error_message[:177]}..."

            # Include compact result summary so the LLM knows what the tool returned
            result_summary = ""
            if bool(tc.get("success", True)):
                result_summary = self._extract_result_summary(tc)

            row = {
                "step": tc.get("step"),
                "tool_name": tc.get("tool_name", "unknown"),
                "focus": focus,
                "success": bool(tc.get("success", True)),
                "error_hint": error_message,
            }
            if result_summary:
                row["result_summary"] = result_summary
            rows.append(row)
        if len(tool_calls) > limit:
            rows.append(
                {
                    "note": (
                        f"{len(tool_calls) - limit} additional steps omitted from prompt "
                        "for compactness; preserve exact order from provided sequence."
                    )
                }
            )
        return json.dumps(rows, ensure_ascii=False, indent=2)

    def _build_rewrite_context_excerpt(
        self,
        messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
    ) -> str:
        """Build a lightweight structural excerpt of the original trajectory.

        Only includes tool names and argument focus hints — NOT the original
        exploration thoughts — to avoid anchoring the LLM to exploration-language
        patterns.
        """
        lines: List[str] = []

        step = 1
        for msg in messages:
            if msg.get("role") != "assistant":
                continue

            tool_calls = msg.get("tool_calls") or []
            if tool_calls:
                for tc in tool_calls:
                    tc_name = tc.get("function", {}).get("name", "unknown")
                    args_raw = tc.get("function", {}).get("arguments", {})
                    if isinstance(args_raw, str):
                        try:
                            args = json.loads(args_raw)
                        except Exception:
                            args = {"raw_arguments": args_raw}
                    elif isinstance(args_raw, dict):
                        args = args_raw
                    else:
                        args = {}
                    focus = self._extract_focus_hint(args)
                    success = tc.get("_tool_result_success", True)
                    error_hint = ""
                    if not success:
                        error_msg = tc.get("_tool_result_error", "")
                        if error_msg:
                            error_hint = f" [FAILED: {str(error_msg)[:100]}]"
                    line = f"Step {step}: tool={tc_name}"
                    if focus:
                        line += f" ({focus})"
                    if error_hint:
                        line += error_hint
                    lines.append(line)
                    step += 1

        if not lines:
            for tc in ordered_tool_calls[: self.rewrite_tool_sequence_max_steps]:
                tc_name = tc.get("tool_name", "unknown")
                focus = self._extract_focus_hint(tc.get("arguments", {}))
                line = f"Step {tc.get('step')}: tool={tc_name}"
                if focus:
                    line += f" ({focus})"
                lines.append(line)

        excerpt = "\n".join(lines)
        if len(excerpt) > self.rewrite_context_max_chars:
            excerpt = excerpt[: self.rewrite_context_max_chars - 3] + "..."
        return excerpt

    def _compress_tool_sequence(
        self,
        ordered_tool_calls: List[Dict[str, Any]],
        messages: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Remove redundant tool calls that don't contribute to data quality.

        A call is considered redundant if:
        1. Same tool + same focus as a previous call (repeated exploration)
        2. The call returned empty/unusable output and no later call depends on it

        Never removes:
        - Calls whose output is referenced by a later call (dependency)
        - The last call in the sequence
        - Calls that are the only representative of their tool type

        Returns:
            (compressed_tool_calls, keep_indices) — subset + indices into original
        """
        if len(ordered_tool_calls) <= 3:
            # Don't compress already-short sequences
            return list(ordered_tool_calls), list(range(len(ordered_tool_calls)))

        # Step 1: Identify output dependencies — which call outputs are used later?
        # We detect this by checking if a later call's arguments overlap with a
        # previous call's focus target.
        focuses: Dict[int, str] = {}  # step → focus hint
        for i, tc in enumerate(ordered_tool_calls):
            args = tc.get("arguments", {})
            focus = self._extract_focus_hint(args)
            if focus:
                focuses[i] = focus

        referenced_by: Dict[int, bool] = {}  # which indices are referenced later
        for i in range(len(ordered_tool_calls)):
            if i not in focuses:
                continue
            ref_focus = focuses[i]
            for j in range(i + 1, len(ordered_tool_calls)):
                j_args_str = self._truncate_text(
                    ordered_tool_calls[j].get("arguments", {})
                ).lower()
                # Check if later call references the same path/target
                if ref_focus and any(
                    part in j_args_str for part in ref_focus.lower().split("=")
                    if len(part) >= 3
                ):
                    referenced_by[i] = True
                    break

        # Step 2: Mark calls to keep
        keep_indices: List[int] = []
        seen_pairs: set = set()  # (tool_name, focus) pairs seen

        for i, tc in enumerate(ordered_tool_calls):
            tool = (tc.get("tool_name") or "").lower()
            focus = focuses.get(i, "")
            pair = (tool, focus)

            # Always keep if:
            is_dependency = referenced_by.get(i, False)  # output used later
            is_last = i == len(ordered_tool_calls) - 1
            has_result = bool(tc.get("success", True)) and tc.get("result")
            is_unique_tool = not any(
                (ordered_tool_calls[j].get("tool_name") or "").lower() == tool
                for j in keep_indices
            )

            if is_dependency or is_last or is_unique_tool:
                keep_indices.append(i)
                seen_pairs.add(pair)
                continue

            # Keep if this is the first time we see this (tool, focus) pair
            if pair not in seen_pairs:
                keep_indices.append(i)
                seen_pairs.add(pair)
                continue

            # Otherwise: redundant exploration call — skip it

        # Safety: always keep at least 50% of original calls
        min_keep = max(3, len(ordered_tool_calls) // 2)
        if len(keep_indices) < min_keep:
            # Add back calls that were removed, preferring successful ones
            removed = [i for i in range(len(ordered_tool_calls)) if i not in keep_indices]
            removed.sort(
                key=lambda idx: (
                    -1 if ordered_tool_calls[idx].get("success", True) else 1,
                    -idx,  # earlier calls first
                )
            )
            while len(keep_indices) < min_keep and removed:
                keep_indices.append(removed.pop(0))
            keep_indices.sort()

        compressed = [ordered_tool_calls[i] for i in keep_indices]

        # Re-number steps
        for new_step, idx in enumerate(keep_indices, start=1):
            compressed[new_step - 1]["step"] = new_step

        removed_count = len(ordered_tool_calls) - len(compressed)
        if removed_count > 0:
            logger.info(
                "Compressed tool sequence: %d → %d calls (removed %d redundant)",
                len(ordered_tool_calls),
                len(compressed),
                removed_count,
            )

        return compressed, keep_indices

    def _segment_trajectory_for_rewrite(
        self,
        ordered_tool_calls: List[Dict[str, Any]],
    ) -> List[List[Dict[str, Any]]]:
        """Split a long tool-call sequence into segments for focused LLM rewriting.

        Uses semantic boundary detection for optimal split points, but enforces
        a hard max segment size to guarantee segmentation for long trajectories.
        """
        segment_size = getattr(self, "rewrite_segment_size", 6)
        max_segment_size = segment_size + 2  # Hard cap: never exceed this many calls
        if len(ordered_tool_calls) <= segment_size:
            return [list(ordered_tool_calls)]

        segments: List[List[Dict[str, Any]]] = []
        current_segment: List[Dict[str, Any]] = []

        for i, tc in enumerate(ordered_tool_calls):
            current_segment.append(tc)

            # Force split at hard max to guarantee segmentation
            if len(current_segment) >= max_segment_size:
                segments.append(current_segment)
                current_segment = []
                continue

            # Prefer semantic boundaries when we have enough calls
            if len(current_segment) >= segment_size and i < len(ordered_tool_calls) - 1:
                next_tc = ordered_tool_calls[i + 1]
                if self._is_semantic_boundary(next_tc, tc):
                    segments.append(current_segment)
                    current_segment = []

        if current_segment:
            segments.append(current_segment)

        # Merge small trailing segments into the previous one
        if len(segments) >= 2 and len(segments[-1]) < 3:
            segments[-2].extend(segments[-1])
            segments.pop()

        return segments

    @staticmethod
    def _is_semantic_boundary(
        current: Dict[str, Any],
        prev: Dict[str, Any],
    ) -> bool:
        """Detect a natural sub-task boundary between two consecutive tool calls.

        Returns True when the two calls likely belong to different logical
        groups — different targets, different operation categories, etc.
        """
        curr_tool = (current.get("tool_name") or "").lower()
        prev_tool = (prev.get("tool_name") or "").lower()

        # Same tool operating on different targets may still be the same logical group
        # e.g., list_directory on /a and /a/b is one exploration phase
        if curr_tool == prev_tool:
            return False

        # Classify tool into high-level operation category
        def _classify(tool: str) -> str:
            retrieve_prefixes = (
                "list_", "get_", "search_", "read_", "fetch_", "lookup_",
                "look_", "find_", "query",
            )
            mutate_keywords = (
                "write", "create", "delete", "remove", "update", "modify",
                "move", "set_", "put_", "post_", "send_", "publish",
                "edit", "add", "insert", "register", "book", "submit",
                "cancel", "revoke", "archive",
            )
            navigate_keywords = ("navigate", "browser_navigate", "go_to")

            for prefix in retrieve_prefixes:
                if tool.startswith(prefix):
                    return "retrieve"
            for kw in navigate_keywords:
                if kw in tool:
                    return "navigate"
            for kw in mutate_keywords:
                if kw in tool:
                    return "mutate"
            return "other"

        prev_class = _classify(prev_tool)
        curr_class = _classify(curr_tool)

        # Transitions between categories indicate semantic boundaries
        if prev_class != curr_class and prev_class != "other" and curr_class != "other":
            return True

        return False

    def _build_segment_rewrite_prompt(
        self,
        problem: str,
        segment: List[Dict[str, Any]],
        segment_index: int,
        total_segments: int,
        running_summary: str,
        reference_answer: str,
        task_type: str,
        critique: str,
        require_plan: bool,
        require_final_answer: bool,
    ) -> str:
        """Build the user prompt for rewriting a single trajectory segment."""
        is_first = segment_index == 1
        is_last = segment_index == total_segments

        # Build tool sequence for this segment with local step numbering
        segment_tool_sequence = []
        for i, tc in enumerate(segment):
            args = tc.get("arguments", {})
            focus = self._extract_focus_hint(args)
            error_message = tc.get("error_message") or ""
            if not error_message and (not bool(tc.get("success", True))):
                error_message = self._truncate_text(tc.get("result", ""))
            error_message = self._truncate_text(error_message)
            if len(error_message) > 180:
                error_message = f"{error_message[:177]}..."

            segment_tool_sequence.append(
                {
                    "step": i + 1,  # Local step numbering
                    "global_step": tc.get("step"),
                    "tool_name": tc.get("tool_name", "unknown"),
                    "focus": focus,
                    "success": bool(tc.get("success", True)),
                    "error_hint": error_message,
                }
            )

        tool_sequence_json = json.dumps(segment_tool_sequence, ensure_ascii=False, indent=2)

        segment_system = (
            "REWRITE_TRAJECTORY_SEGMENT_SYSTEM_PROMPT"
        )
        segment_user_template = (
            "REWRITE_TRAJECTORY_SEGMENT_USER_TEMPLATE"
        )

        # These keys will be resolved from prompt_bundle by the caller
        segment_prompt = """Task type: {task_type}
Problem: {problem}
Planning required: {require_plan}
Final answer required: {require_final_answer}

Segment {segment_index} of {total_segments} (first={is_first}, last={is_last})

Running context from previous segments:
{running_summary}

Tool calls in this segment (ground truth):
{tool_sequence_json}

Reference answer:
{reference_answer}

Previous judge feedback:
{critique}

Style requirements:
- Each thought should name the specific action and connect it to the user's request
- Prefer concrete references to the task goal over generic exploration language
- Avoid phrases like "to inform the next decision" or "before deciding next steps"
- Use direct task-execution language: "to retrieve/find/create/update the X the user asked about"

Output JSON only in the required schema."""

        return segment_prompt.format(
            task_type=task_type,
            problem=problem,
            require_plan=str(require_plan).lower(),
            require_final_answer=str(require_final_answer).lower(),
            segment_index=segment_index,
            total_segments=total_segments,
            is_first=str(is_first).lower(),
            is_last=str(is_last).lower(),
            running_summary=running_summary or "This is the first segment — no prior context.",
            tool_sequence_json=tool_sequence_json,
            reference_answer=self._truncate_text(reference_answer or "N/A"),
            critique=critique or "N/A",
        )

    def _parse_json_from_response(self, response: str) -> Any:
        match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            match = re.search(r"(\{.*\}|\[.*\])", response, re.DOTALL)
            if match:
                json_str = match.group(1)
            else:
                json_str = response

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from response: %s...", response[:100])
            return {}

    async def _judge_problem(
        self,
        problem: str,
        summary: str,
        prompt_bundle: Dict[str, str],
        task_type: str,
    ) -> Tuple[bool, str]:
        prompt = prompt_bundle["JUDGE_PROBLEM_USER_TEMPLATE"].format(
            problem=problem,
            trajectory_summary=summary,
            task_type=task_type,
        )
        try:
            resp_str = await self.client.generate_text(
                prompt,
                self.judge_model,
                system_prompt=prompt_bundle["JUDGE_PROBLEM_SYSTEM_PROMPT"],
            )
            data = self._parse_json_from_response(resp_str)
            if not isinstance(data, dict):
                return False, "Judge returned non-JSON-object response"
            return bool(data.get("consistent", False)), data.get(
                "reason", "No reason provided"
            )
        except Exception as e:
            logger.warning("Judge 1 Error: %s", e)
            return False, str(e)

    async def _refine_problem(
        self,
        problem: str,
        summary: str,
        critique: str,
        prompt_bundle: Dict[str, str],
    ) -> str:
        prompt = prompt_bundle["REFINE_PROBLEM_USER_TEMPLATE"].format(
            original_problem=problem,
            trajectory_summary=summary,
            critique=critique,
        )
        return await self.client.generate_text(
            prompt,
            self.rewrite_model,
            system_prompt=prompt_bundle["REFINE_PROBLEM_SYSTEM_PROMPT"],
        )

    async def _call_judge_model(
        self,
        system_prompt: str,
        user_prompt: str,
        use_relaxed: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Helper to call judge model and parse JSON response.

        Args:
            use_relaxed: If True, use the relaxed-temperature judge model.
        Returns:
            Parsed JSON dict, or None if call failed
        """
        model = self.judge_model_relaxed if use_relaxed else self.judge_model
        try:
            resp_str = await self.client.generate_text(
                user_prompt,
                model,
                system_prompt=system_prompt,
            )
            data = self._parse_json_from_response(resp_str)
            if not isinstance(data, dict):
                return None
            return data
        except Exception as e:
            logger.warning("Judge model call error: %s", e)
            return None

    async def _judge_trajectory(
        self,
        problem: str,
        full_traj: str,
        required_tool_steps: int,
        prompt_bundle: Dict[str, str],
        task_type: str,
        reference_answer: str,
    ) -> Tuple[bool, str]:
        prompt = prompt_bundle["JUDGE_TRAJECTORY_USER_TEMPLATE"].format(
            problem=problem,
            trajectory_full=full_traj,
            required_tool_steps=required_tool_steps,
            require_plan=str(self.require_planning_step).lower(),
            require_final_answer=str(self.require_final_answer).lower(),
            task_type=task_type,
            reference_answer=self._truncate_text(reference_answer or "N/A"),
        )
        try:
            resp_str = await self.client.generate_text(
                prompt,
                self.judge_model,
                system_prompt=prompt_bundle["JUDGE_TRAJECTORY_SYSTEM_PROMPT"],
            )
            data = self._parse_json_from_response(resp_str)
            if not isinstance(data, dict):
                return False, "Judge returned non-JSON-object response"
            return bool(data.get("realistic", False)), data.get(
                "reason", "No reason provided"
            )
        except Exception as e:
            logger.warning("Judge 2 Error: %s", e)
            return False, str(e)

    async def _rewrite_trajectory_with_structure(
        self,
        problem: str,
        messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        reference_answer: str,
        task_type: str,
        critique: str,
        prompt_bundle: Dict[str, str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Rewrite trajectory with LLM, using segmented approach for long sequences.

        For short trajectories (<= segment_size), use single-pass rewrite.
        For longer ones, split into segments with running context summaries to
        avoid attention dilution from oversized prompts.
        """
        # Compress redundant exploration calls if enabled
        if (
            getattr(self, "compress_tool_sequence", False)
            and len(ordered_tool_calls) > 3
        ):
            compressed_calls, _keep_indices = self._compress_tool_sequence(
                ordered_tool_calls, messages
            )
            if len(compressed_calls) < len(ordered_tool_calls):
                ordered_tool_calls = compressed_calls

        segment_size = getattr(self, "rewrite_segment_size", 6)

        if len(ordered_tool_calls) <= segment_size:
            return await self._rewrite_trajectory_single_pass(
                problem=problem,
                messages=messages,
                ordered_tool_calls=ordered_tool_calls,
                reference_answer=reference_answer,
                task_type=task_type,
                critique=critique,
                prompt_bundle=prompt_bundle,
            )

        # Segmented rewrite for long trajectories
        return await self._rewrite_trajectory_segmented(
            problem=problem,
            messages=messages,
            ordered_tool_calls=ordered_tool_calls,
            reference_answer=reference_answer,
            task_type=task_type,
            critique=critique,
            prompt_bundle=prompt_bundle,
        )

    async def _rewrite_trajectory_single_pass(
        self,
        problem: str,
        messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        reference_answer: str,
        task_type: str,
        critique: str,
        prompt_bundle: Dict[str, str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Single-pass LLM rewrite for short trajectories (<= segment_size steps)."""
        prompt = prompt_bundle["REWRITE_TRAJECTORY_USER_TEMPLATE"].format(
            problem=problem,
            require_plan=str(self.require_planning_step).lower(),
            require_final_answer=str(self.require_final_answer).lower(),
            tool_sequence_json=self._build_tool_sequence_for_prompt(ordered_tool_calls),
            original_trajectory_excerpt=self._build_rewrite_context_excerpt(
                messages=messages,
                ordered_tool_calls=ordered_tool_calls,
            ),
            reference_answer=self._truncate_text(reference_answer or "N/A"),
            critique=critique or "N/A",
            task_type=task_type,
        )
        try:
            resp_str = await self.client.generate_text(
                prompt,
                self.rewrite_model,
                system_prompt=prompt_bundle["REWRITE_TRAJECTORY_SYSTEM_PROMPT"],
            )

            data = self._parse_json_from_response(resp_str)
            if not isinstance(data, dict):
                return None

            return self._apply_structured_rewrite(
                original_messages=messages,
                rewrite_payload=data,
                required_tool_steps=len(ordered_tool_calls),
                ordered_tool_calls=ordered_tool_calls,
                problem=problem,
                reference_answer=reference_answer,
                task_type=task_type,
            )
        except Exception as e:
            logger.warning("Rewrite Trajectory Error (single-pass): %s", e)
            return None

    async def _rewrite_trajectory_segmented(
        self,
        problem: str,
        messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        reference_answer: str,
        task_type: str,
        critique: str,
        prompt_bundle: Dict[str, str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Segment-based rewrite for long trajectories.

        Splits the tool sequence into segments, rewrites each with a running
        context summary from prior segments, then reassembles the full result.
        """
        segments = self._segment_trajectory_for_rewrite(ordered_tool_calls)
        total_segments = len(segments)
        logger.info(
            "Segmented rewrite: %d tool calls → %d segments (max %d per segment)",
            len(ordered_tool_calls),
            total_segments,
            getattr(self, "rewrite_segment_size", 6),
        )

        all_thoughts: Dict[int, str] = {}  # global_step → thought
        running_summary = ""
        final_response = ""
        plan = ""

        segment_system_prompt = prompt_bundle.get(
            "REWRITE_TRAJECTORY_SEGMENT_SYSTEM_PROMPT",
            prompt_bundle["REWRITE_TRAJECTORY_SYSTEM_PROMPT"],
        )
        segment_user_template = prompt_bundle.get(
            "REWRITE_TRAJECTORY_SEGMENT_USER_TEMPLATE",
        )

        for seg_idx, segment in enumerate(segments):
            is_first = seg_idx == 0
            is_last = seg_idx == total_segments - 1

            if segment_user_template:
                seg_prompt = segment_user_template.format(
                    task_type=task_type,
                    problem=problem,
                    require_plan=str(self.require_planning_step and is_first).lower(),
                    require_final_answer=str(self.require_final_answer and is_last).lower(),
                    segment_index=seg_idx + 1,
                    total_segments=total_segments,
                    is_first=str(is_first).lower(),
                    is_last=str(is_last).lower(),
                    running_summary=running_summary or "Task start — no prior segments.",
                    tool_sequence_json=self._build_tool_sequence_for_prompt(segment),
                    reference_answer=self._truncate_text(
                        reference_answer if is_last else "N/A"
                    ),
                    critique=critique if is_first else "N/A",
                )
            else:
                seg_prompt = self._build_segment_rewrite_prompt(
                    problem=problem,
                    segment=segment,
                    segment_index=seg_idx + 1,
                    total_segments=total_segments,
                    running_summary=running_summary,
                    reference_answer=reference_answer if is_last else "",
                    task_type=task_type,
                    critique=critique if is_first else "",
                    require_plan=self.require_planning_step and is_first,
                    require_final_answer=self.require_final_answer and is_last,
                )

            try:
                resp_str = await self.client.generate_text(
                    seg_prompt,
                    self.rewrite_model,
                    system_prompt=segment_system_prompt,
                )
            except Exception as e:
                logger.warning(
                    "Segment %d/%d rewrite failed: %s", seg_idx + 1, total_segments, e
                )
                continue

            seg_data = self._parse_json_from_response(resp_str)
            if not isinstance(seg_data, dict):
                logger.warning(
                    "Segment %d/%d returned non-dict response", seg_idx + 1, total_segments
                )
                continue

            # Map local steps to global steps
            for step_entry in seg_data.get("steps", []):
                if not isinstance(step_entry, dict):
                    continue
                local_step = step_entry.get("step")
                thought = str(step_entry.get("thought", "")).strip()
                if local_step is not None and thought:
                    # Map local step number → global step from ordered_tool_calls
                    local_idx = int(local_step) - 1
                    if local_idx < len(segment):
                        global_step = segment[local_idx].get(
                            "step", seg_idx * getattr(self, "rewrite_segment_size", 6) + local_idx + 1
                        )
                        all_thoughts[int(global_step)] = thought

            # Extract running summary for next segment
            running_summary = str(seg_data.get("segment_summary", "")).strip()
            if not running_summary and is_last:
                # Auto-generate summary from tool sequence if LLM didn't provide one
                tools_called = [tc.get("tool_name", "?") for tc in segment]
                success_count = sum(1 for tc in segment if tc.get("success", True))
                running_summary = (
                    f"Segment {seg_idx + 1}: called {', '.join(tools_called[:8])}"
                    f"{'...' if len(tools_called) > 8 else ''} "
                    f"({success_count}/{len(segment)} succeeded)."
                )

            # Extract final_response from last segment
            if is_last:
                final_response = str(seg_data.get("final_response", "")).strip()

            # Extract plan from first segment
            if is_first:
                plan = str(seg_data.get("plan", "")).strip()

        if not all_thoughts:
            logger.warning("Segmented rewrite produced no valid thoughts")
            return None

        # Build combined payload for _apply_structured_rewrite
        combined_steps = [
            {"step": step, "thought": thought}
            for step, thought in sorted(all_thoughts.items())
        ]
        combined_payload = {
            "plan": plan,
            "steps": combined_steps,
            "final_response": final_response,
        }

        return self._apply_structured_rewrite(
            original_messages=messages,
            rewrite_payload=combined_payload,
            required_tool_steps=len(ordered_tool_calls),
            ordered_tool_calls=ordered_tool_calls,
            problem=problem,
            reference_answer=reference_answer,
            task_type=task_type,
        )

    async def _polish_fallback_trajectory(
        self,
        fallback_messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        problem: str,
        reference_answer: str,
        task_type: str,
        require_plan: bool,
        require_final_answer: bool,
        critique: str,
        prompt_bundle: Dict[str, str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Polish rule-generated fallback trajectory with LLM.

        For long trajectories, sends only the thought skeleton (without full tool
        outputs) to avoid attention dilution. The complete tool outputs are already
        present in tool_sequence_json.
        """
        polish_system = prompt_bundle.get("POLISH_FALLBACK_TRAJECTORY_SYSTEM_PROMPT", "")
        polish_user_template = prompt_bundle.get("POLISH_FALLBACK_TRAJECTORY_USER_TEMPLATE", "")

        if not polish_system or not polish_user_template:
            logger.warning("Polish prompts not available, skipping polish")
            return None

        # Use compact serialization for long trajectories to avoid context overload
        segment_size = getattr(self, "rewrite_segment_size", 6)
        if len(ordered_tool_calls) > segment_size:
            # Compact: only include assistant thoughts + tool call names, not full outputs
            compact_msgs = []
            step_idx = 1
            for msg in fallback_messages:
                if msg.get("role") == "assistant":
                    compact_msgs.append({
                        "role": "assistant",
                        "content": msg.get("content", ""),
                        "tool_calls": [
                            {"function": {"name": tc.get("function", {}).get("name", "?")}}
                            for tc in (msg.get("tool_calls") or [])
                        ] if msg.get("tool_calls") else None,
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
        else:
            fallback_messages_json = json.dumps(fallback_messages, ensure_ascii=False, indent=2)

        # Serialize tool sequence for global context
        tool_sequence_json = json.dumps(ordered_tool_calls, ensure_ascii=False, indent=2)

        # Format user prompt with full global context
        polish_user = polish_user_template.format(
            problem=problem,
            task_type=task_type,
            require_plan=require_plan,
            require_final_answer=require_final_answer,
            tool_sequence_json=tool_sequence_json,
            fallback_messages_json=fallback_messages_json,
            reference_answer=reference_answer or "N/A",
            critique=critique or "N/A",
        )

        try:
            resp_str = await self.client.generate_text(
                polish_user,
                self.polish_model,
                system_prompt=polish_system,
            )

            polish_payload = self._parse_json_from_response(resp_str)
            if not isinstance(polish_payload, dict):
                logger.warning("Polish response is not a dict")
                return None

            polished_messages = self._apply_structured_rewrite(
                original_messages=fallback_messages,
                rewrite_payload=polish_payload,
                required_tool_steps=len(ordered_tool_calls),
                ordered_tool_calls=ordered_tool_calls,
                problem=problem,
                reference_answer=reference_answer,
                task_type=task_type,
            )

            return polished_messages

        except Exception as e:
            logger.warning("Polish Fallback Trajectory Error: %s", e)
            return None

    def _apply_structured_rewrite(
        self,
        original_messages: List[Dict[str, Any]],
        rewrite_payload: Dict[str, Any],
        required_tool_steps: int,
        ordered_tool_calls: List[Dict[str, Any]],
        problem: str,
        reference_answer: str,
        task_type: str,
    ) -> Optional[List[Dict[str, Any]]]:
        steps_data = rewrite_payload.get("steps")
        if not isinstance(steps_data, list):
            return None

        plan = (rewrite_payload.get("plan", "") or "").strip()
        final_response = (rewrite_payload.get("final_response", "") or "").strip()

        thought_by_step: Dict[int, str] = {}
        for row in steps_data:
            if not isinstance(row, dict):
                continue
            try:
                step_id = int(row.get("step"))
            except Exception:
                continue
            thought = str(row.get("thought", "")).strip()
            if step_id > 0 and thought:
                thought_by_step[step_id] = thought

        if required_tool_steps > 0 and not thought_by_step:
            for required_step in range(1, required_tool_steps + 1):
                thought_by_step[required_step] = self._default_step_thought(
                    required_step, ordered_tool_calls
                )
        final_response = self._postprocess_final_response(
            final_response=final_response,
            task_type=task_type,
            reference_answer=reference_answer,
            ordered_tool_calls=ordered_tool_calls,
            problem=problem,
        )
        if self.require_final_answer and not final_response:
            final_response = self._default_final_response(
                ordered_tool_calls, reference_answer, task_type
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

        # If tool-call assistant message was not found, we still keep original structure.
        if self.require_planning_step and not first_tool_assistant_written:
            return None

        if self.require_final_answer or final_response:
            # Final response must appear only after the last tool-use turn.
            # Some raw trajectories contain empty assistant placeholders before
            # the final tool call; writing final_response there causes
            # "answered-before-finished" failures in Stage2 judge.
            last_tool_turn_idx = -1
            for idx, msg in enumerate(rewritten):
                if msg.get("role") == "assistant" and msg.get("tool_calls"):
                    last_tool_turn_idx = idx

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
            elif self.require_final_answer and not final_written and not final_response:
                return None

        # Enforce one reasoning thought per tool-use step.
        if required_tool_steps > 0:
            for required_step in range(1, required_tool_steps + 1):
                if required_step not in thought_by_step:
                    thought_by_step[required_step] = self._default_step_thought(
                        required_step, ordered_tool_calls
                    )

        return rewritten

    @staticmethod
    def _infer_tool_intent(tool_name: str) -> str:
        low = (tool_name or "").lower()
        for match_type, keywords, intent in fallback_prompts.TOOL_INTENT_RULES:
            if match_type == "exact":
                if any(low == key.lower() for key in keywords):
                    return intent
            else:
                if any(key.lower() in low for key in keywords):
                    return intent
        return fallback_prompts.GENERIC_TOOL_INTENT

    @staticmethod
    def _extract_focus_hint(arguments: Any) -> str:
        if not isinstance(arguments, dict) or not arguments:
            return ""

        preferred_keys = [
            "path",
            "source",
            "destination",
            "url",
            "query",
            "pattern",
            "name",
            "database",
            "table",
        ]
        for key in preferred_keys:
            if key not in arguments:
                continue
            value = arguments.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, (dict, list)):
                try:
                    text = json.dumps(value, ensure_ascii=False)
                except Exception:
                    text = str(value)
            else:
                text = str(value)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 80:
                text = f"{text[:77]}..."
            return f"{key}={text}"
        return ""

    @staticmethod
    def _summarize_items_for_problem(items: List[str], limit: int = 4) -> str:
        cleaned = [str(i).strip() for i in items if str(i).strip()]
        if not cleaned:
            return ""
        shown = cleaned[:limit]
        text = ", ".join(shown)
        remaining = len(cleaned) - len(shown)
        if remaining > 0:
            text += f", and {remaining} more"
        return text

    def _build_grounded_mutation_problem(
        self, ordered_tool_calls: List[Dict[str, Any]]
    ) -> str:
        created_dirs: List[str] = []
        touched_files: List[str] = []
        moved_pairs: List[str] = []
        deleted_paths: List[str] = []

        def _dedup_append(target: List[str], value: str) -> None:
            v = (value or "").strip()
            if not v:
                return
            if v not in target:
                target.append(v)

        for tc in ordered_tool_calls:
            if not bool(tc.get("success", True)):
                continue
            tool = str(tc.get("tool_name", "") or "").lower()
            args = tc.get("arguments", {})
            if not isinstance(args, dict):
                continue

            if "create_directory" in tool:
                _dedup_append(created_dirs, str(args.get("path", "") or ""))
                continue

            if any(k in tool for k in ("write_file", "edit_file", "append_file", "touch_file")):
                _dedup_append(touched_files, str(args.get("path", "") or ""))
                continue

            if "move_file" in tool or "rename" in tool:
                src = str(
                    args.get("source")
                    or args.get("old_path")
                    or args.get("src")
                    or ""
                ).strip()
                dst = str(
                    args.get("destination")
                    or args.get("new_path")
                    or args.get("dst")
                    or ""
                ).strip()
                if src and dst:
                    _dedup_append(moved_pairs, f"{src} -> {dst}")
                continue

            if "delete" in tool or "remove" in tool:
                _dedup_append(
                    deleted_paths,
                    str(
                        args.get("path")
                        or args.get("target")
                        or args.get("source")
                        or ""
                    ),
                )

        parts: List[str] = []
        if created_dirs:
            parts.append(
                "create directories " + self._summarize_items_for_problem(created_dirs)
            )
        if touched_files:
            parts.append(
                "create or update files "
                + self._summarize_items_for_problem(touched_files)
            )
        if moved_pairs:
            parts.append("move/rename files " + self._summarize_items_for_problem(moved_pairs))
        if deleted_paths:
            parts.append("delete files " + self._summarize_items_for_problem(deleted_paths))

        if not parts:
            return ""
        if len(parts) == 1:
            return f"Please {parts[0]}."
        if len(parts) == 2:
            return f"Please {parts[0]}, then {parts[1]}."
        return f"Please {parts[0]}, then {parts[1]}, and finally {parts[2]}."

    @staticmethod
    def _token_overlap_ratio(reference: str, candidate: str) -> float:
        ref_tokens = {
            t for t in re.findall(r"[a-z0-9_./-]+", (reference or "").lower()) if len(t) >= 3
        }
        if not ref_tokens:
            return 1.0
        cand = (candidate or "").lower()
        hit = sum(1 for t in ref_tokens if t in cand)
        return hit / max(1, len(ref_tokens))

    @staticmethod
    def _extract_workspace_paths(text: str) -> List[str]:
        if not text:
            return []
        matches = re.findall(r"/workspace(?:/[A-Za-z0-9._-]+)+", text)
        deduped: List[str] = []
        for raw in matches:
            normalized = re.sub(r"/{2,}", "/", raw.strip())
            normalized = normalized.rstrip(".,;:!?)]}\"'")
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped

    @staticmethod
    def _extract_problem_path_hint(problem: str) -> str:
        match = re.search(r"/workspace(?:/[A-Za-z0-9._-]+)*", problem or "")
        if not match:
            return ""
        path = match.group(0).rstrip("/")
        return path or "/workspace"

    def _is_listing_retrieval_query(self, problem: str, reference_answer: str) -> bool:
        text = f"{problem or ''}\n{reference_answer or ''}".lower()

        listing_phrases_en = [
            "what files",
            "which files",
            "directory structure",
            "what's inside",
            "what is inside",
            "files in",
            "folders in",
        ]
        listing_verbs_en = [
            "list",
            "show",
            "enumerate",
            "display",
        ]
        listing_nouns_en = [
            "files",
            "file",
            "folders",
            "folder",
            "directory",
            "directories",
            "tree",
            "structure",
            "workspace",
            "root",
            "contents",
        ]
        listing_phrases_zh = [
            "都有哪些文件",
            "目录结构",
            "文件列表",
            "里面有什么文件",
            "工作区里有哪些",
        ]
        listing_verbs_zh = [
            "列出",
            "列一下",
            "清单",
            "展示",
            "查看",
        ]
        listing_nouns_zh = [
            "文件",
            "目录",
            "文件夹",
            "结构",
            "根目录",
            "工作区",
        ]
        if any(marker in text for marker in listing_phrases_en + listing_phrases_zh):
            return True
        if (
            any(marker in text for marker in listing_verbs_en)
            and any(marker in text for marker in listing_nouns_en)
        ):
            return True
        if (
            any(marker in text for marker in listing_verbs_zh)
            and any(marker in text for marker in listing_nouns_zh)
        ):
            return True

        return len(self._extract_workspace_paths(reference_answer or "")) >= 6

    def _collect_retrieval_evidence_items(
        self, ordered_tool_calls: List[Dict[str, Any]], problem: str
    ) -> List[str]:
        if not ordered_tool_calls:
            return []

        listing_tool_markers = [
            "search",
            "list",
            "tree",
            "directory",
            "glob",
            "find",
            "ls",
        ]
        error_markers = ["mcp error", "validation error", "traceback", "failed", "tool execution error", "no active episode"]

        evidence_items: List[str] = []
        for tc in ordered_tool_calls:
            if not bool(tc.get("success", True)):
                continue

            result_text = self._truncate_text(tc.get("result", "") or "")
            if not result_text.strip():
                continue
            if any(marker in result_text.lower() for marker in error_markers):
                continue

            paths = self._extract_workspace_paths(result_text)
            if not paths:
                continue

            tool_name = str(tc.get("tool_name", "") or "").lower()
            if len(paths) >= 3 or any(marker in tool_name for marker in listing_tool_markers):
                evidence_items.extend(paths)

        deduped: List[str] = []
        for item in evidence_items:
            if item not in deduped:
                deduped.append(item)

        path_hint = self._extract_problem_path_hint(problem)
        if path_hint and path_hint != "/workspace":
            path_hint_with_sep = f"{path_hint}/"
            filtered = [
                p for p in deduped if p == path_hint or p.startswith(path_hint_with_sep)
            ]
            if len(filtered) >= 3:
                deduped = filtered

        return deduped

    def _check_retrieval_answer_completeness(
        self,
        final_answer: str,
        problem: str,
        reference_answer: str,
        ordered_tool_calls: List[Dict[str, Any]],
    ) -> Tuple[bool, str]:
        if not self._is_listing_retrieval_query(problem, reference_answer):
            return True, "not a listing-style retrieval query"

        evidence_items = self._collect_retrieval_evidence_items(ordered_tool_calls, problem)
        if len(evidence_items) < 8:
            return True, "insufficient list evidence for completeness gating"

        answer_text = (final_answer or "").strip().lower()
        if not answer_text:
            return False, "retrieval listing answer is empty"

        matched = 0
        for path in evidence_items:
            low_path = path.lower()
            basename = os.path.basename(low_path)
            if low_path in answer_text or (basename and basename in answer_text):
                matched += 1
        coverage = matched / max(1, len(evidence_items))
        if coverage < 0.75:
            return (
                False,
                "retrieval answer is incomplete for listing/search evidence "
                f"(matched {matched}/{len(evidence_items)} items)",
            )
        return True, "retrieval listing coverage is sufficient"

    def _postprocess_final_response(
        self,
        final_response: str,
        task_type: str,
        reference_answer: str,
        ordered_tool_calls: List[Dict[str, Any]],
        problem: str = "",
    ) -> str:
        text = (final_response or "").strip()
        normalized_task_type = str(task_type).lower()

        if normalized_task_type == TaskType.RETRIEVAL.value:
            # For listing-style retrieval tasks, auto-repair partial final answers by
            # materializing the full evidence-backed item set.
            if self._is_listing_retrieval_query(problem, reference_answer):
                evidence_items = self._collect_retrieval_evidence_items(
                    ordered_tool_calls, problem
                )
                if len(evidence_items) >= 8:
                    complete_listing = "\n".join(evidence_items)
                    completeness_ok, _ = self._check_retrieval_answer_completeness(
                        final_answer=text,
                        problem=problem,
                        reference_answer=reference_answer,
                        ordered_tool_calls=ordered_tool_calls,
                    )
                    if not text or not completeness_ok:
                        return (
                            "Based on the observed tool outputs, the complete matched items are:\n"
                            + complete_listing
                        )
            if reference_answer:
                # Ensure retrieval final response is strongly grounded, even when
                # model-generated text is partial or drifts after noisy retries.
                overlap = self._token_overlap_ratio(reference_answer, text)
                if (not text) or overlap < 0.2:
                    return (
                        "Based on the observed tool outputs, here is the retrieval result:\n"
                        + self._truncate_text(reference_answer)
                    )
            return text or self._default_final_response(
                ordered_tool_calls, reference_answer, task_type
            )

        if normalized_task_type == TaskType.MUTATION.value:
            if not text:
                return self._default_final_response(
                    ordered_tool_calls, reference_answer, task_type
                )

            lowered = text.lower()
            incomplete_markers = [
                "i should ",
                "you should ",
                "next step",
                "i need to ",
                "not complete",
                "not completed",
                "unable to",
                "cannot",
                "can't",
                "if you want",
                "you can",
            ]
            if any(marker in lowered for marker in incomplete_markers):
                return self._default_final_response(
                    ordered_tool_calls, reference_answer, task_type
                )

        return text or self._default_final_response(
            ordered_tool_calls, reference_answer, task_type
        )

    @staticmethod
    def _default_plan_thought(problem: str, task_type: str) -> str:
        task_hint = "retrieval" if str(task_type).lower() == TaskType.RETRIEVAL.value else "execution"
        objective = (problem or "").strip()
        if len(objective) > 100:
            objective = f"{objective[:97]}..."
        if objective:
            return fallback_prompts.DEFAULT_PLAN_WITH_OBJECTIVE_TEMPLATE.format(
                task_hint=task_hint,
                objective=objective,
            )
        return fallback_prompts.DEFAULT_PLAN_WITHOUT_OBJECTIVE

    def _default_step_thought(
        self, step: int, ordered_tool_calls: List[Dict[str, Any]]
    ) -> str:
        if 1 <= step <= len(ordered_tool_calls):
            tc = ordered_tool_calls[step - 1]
            tool = tc.get("tool_name", "unknown")
            args = tc.get("arguments", {})
            intent = self._infer_tool_intent(tool)
            focus = self._extract_focus_hint(args)

            prev_failed = False
            if step > 1 and (step - 2) < len(ordered_tool_calls):
                prev_failed = not bool(ordered_tool_calls[step - 2].get("success", True))

            if prev_failed:
                retry_variants = getattr(
                    fallback_prompts, "DEFAULT_RETRY_THOUGHT_VARIANTS", None
                )
                if retry_variants:
                    base = retry_variants[(step - 1) % len(retry_variants)]
                else:
                    base = fallback_prompts.DEFAULT_RETRY_THOUGHT
            else:
                variants = [
                    template.format(intent=intent)
                    for template in fallback_prompts.DEFAULT_STEP_THOUGHT_VARIANTS
                ]
                base = variants[(step - 1) % len(variants)]

            if focus:
                return f"{base}{fallback_prompts.DEFAULT_FOCUS_SUFFIX_TEMPLATE.format(focus=focus)}"
            return base
        return fallback_prompts.GENERIC_NEXT_STEP_THOUGHT

    def _default_final_response(
        self,
        ordered_tool_calls: List[Dict[str, Any]],
        reference_answer: str,
        task_type: str,
    ) -> str:
        if reference_answer:
            if str(task_type).lower() == TaskType.RETRIEVAL.value:
                return f"I have completed the retrieval task. Answer: {self._truncate_text(reference_answer)}"
            return self._truncate_text(reference_answer)
        success_cnt = sum(1 for tc in ordered_tool_calls if tc.get("success", True))
        total_cnt = len(ordered_tool_calls)
        if total_cnt == 0:
            if str(task_type).lower() == TaskType.RETRIEVAL.value:
                return "I have completed the retrieval task, but there was no observable retrieval evidence to answer with certainty."
            return "I have completed the task with no tool calls required."
        # Build a concise action summary: tool_name + success/failure for each call
        action_items = []
        for tc in ordered_tool_calls:
            tool_name = tc.get("tool_name", "unknown_tool")
            success = tc.get("success", True)
            status = "done" if success else "failed"
            # Extract compact result when available
            result_val = tc.get("result_summary", "") or self._extract_result_summary(tc)
            if result_val:
                short = str(result_val).strip()[:80]
                action_items.append(f"{tool_name}: {status} → {short}")
            else:
                action_items.append(f"{tool_name}: {status}")
        summary = "; ".join(action_items) if action_items else "no actions taken"
        if str(task_type).lower() == TaskType.RETRIEVAL.value:
            return (
                f"I have completed the retrieval task based on observed tool outputs. "
                f"Successful calls: {success_cnt}/{total_cnt}. "
                f"Actions: {summary}"
            )
        return (
            f"Here is what happened based on the tool outputs: {summary}. "
            f"({success_cnt}/{total_cnt} calls succeeded)"
        )

    def _build_structured_fallback_messages(
        self,
        messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        problem: str,
        reference_answer: str,
        task_type: str,
    ) -> Optional[List[Dict[str, Any]]]:
        rewritten = [dict(m) for m in messages]
        if not rewritten:
            return None

        # Replace the first user message content with the synthesized problem.
        # The original messages contain the collection-phase problem which may
        # differ from the synthesized one. The judge evaluates against the
        # synthesized problem, so they must match.
        for msg in rewritten:
            if msg.get("role") == "user":
                msg["content"] = problem
                break

        step_idx = 1
        first_tool_assistant_seen = False
        plan_text = self._default_plan_thought(problem, task_type)
        for msg in rewritten:
            if msg.get("role") != "assistant" or not msg.get("tool_calls"):
                continue

            thoughts: List[str] = []
            if not first_tool_assistant_seen and plan_text:
                thoughts.append(plan_text)
                first_tool_assistant_seen = True

            call_count = len(msg.get("tool_calls") or [])
            for _ in range(call_count):
                thoughts.append(self._default_step_thought(step_idx, ordered_tool_calls))
                step_idx += 1
            msg["content"] = "\n".join(thoughts)

        final_text = self._default_final_response(
            ordered_tool_calls, reference_answer, task_type
        )
        last_tool_turn_idx = -1
        for idx, msg in enumerate(rewritten):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                last_tool_turn_idx = idx

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
                msg["content"] = final_text
                final_written = True
                break
        if not final_written:
            rewritten.append({"role": "assistant", "content": final_text})
        return rewritten

    def _heuristic_problem_check(
        self, problem: str, expected_tool_steps: int, task_type: str,
        collection_task_type: Optional[str] = None,
    ) -> Tuple[bool, str]:
        text = (problem or "").strip()
        if not text:
            return False, "empty problem"
        if len(text) < 20:
            return False, "problem too short"
        lowered = text.lower()
        meta_markers = [
            "rewrite the",
            "trajectory",
            "ground truth",
            "critique",
            "previous problem",
            "tool call",
            "output json",
        ]
        if any(marker in lowered for marker in meta_markers):
            return False, "problem contains meta-instructions"
        if expected_tool_steps <= 0 and "tool" in lowered:
            return False, "tool-specific wording with no tool evidence"

        # When collection-phase task_type (from diff analysis) is available and
        # matches, trust the authoritative determination — skip heuristic re-check.
        normalized_task_type = str(task_type).lower()
        if collection_task_type and str(collection_task_type).lower() == normalized_task_type:
            return True, "problem is user-facing and task-type-aligned (collection type trusted)"

        # Fallback heuristic check when collection_task_type is unavailable or mismatched.
        question_like = bool(
            re.search(r"[?？]\s*$", text)
            or re.match(
                r"^\s*(what|which|who|where|when|why|how|is|are|can|does|do|could|would|should)\b",
                lowered,
            )
        )
        retrieval_style_markers = [
            "what evidence",
            "is there evidence",
            "whether",
            "is any",
            "are any",
            "what's inside",
            "what is inside",
            "what does",
        ]

        mutation_verbs = [
            "turn on", "turn off", "switch on", "switch off",
            "enable", "disable", "activate", "deactivate",
            "set", "change", "update", "modify", "toggle",
            "delete", "remove", "add", "create", "install", "uninstall",
            "send", "kill", "clear", "wipe", "reset", "stop", "start",
            "fix", "convert", "transfer", "move", "copy", "replace",
            "register", "unregister", "dump",
        ]

        if normalized_task_type == TaskType.MUTATION.value:
            has_mutation_verb = any(verb in lowered for verb in mutation_verbs)
            if (question_like or any(marker in lowered for marker in retrieval_style_markers)) and not has_mutation_verb:
                return False, "mutation task became retrieval-style question"
        elif normalized_task_type == TaskType.RETRIEVAL.value:
            retrieval_request_markers = [
                "list",
                "show",
                "find",
                "tell",
                "summarize",
                "report",
                "identify",
            ]
            if (not question_like) and (
                not any(marker in lowered for marker in retrieval_request_markers)
            ):
                return False, "retrieval task is not phrased as an information request"

        return True, "problem is user-facing and task-type-aligned"

    @staticmethod
    def _is_problem_refine_low_yield(reason: str, task_type: str) -> bool:
        lowered = (reason or "").lower()
        if not lowered:
            return False

        # If the judge says evidence is missing/empty, repeated refine loops usually
        # cannot recover because this is determined by fixed trajectory evidence.
        evidence_missing_markers = [
            "no trajectory evidence",
            "no observable trajectory evidence",
            "no evidence is provided",
            "no evidence of",
            "no trajectory evidence to support",
            "no trajectory evidence supports",
            "empty summary",
            "placeholder summary",
            "not answerable from evidence",
            "cannot be verified against observed actions",
            "not supported by observed",
            "not grounded in observed evidence",
        ]
        if any(marker in lowered for marker in evidence_missing_markers):
            return True

        normalized_task_type = str(task_type).lower()
        if normalized_task_type == TaskType.MUTATION.value:
            if "task type is mutation" in lowered and "retrieval" in lowered:
                return True
        return False

    @staticmethod
    def _is_trajectory_refine_low_yield(reason: str) -> bool:
        lowered = (reason or "").lower()
        if not lowered:
            return False

        # Rewriting thoughts cannot fix immutable mismatches in tool calls/results.
        if "tool-step count mismatch" in lowered:
            return True
        if "missing tool outputs" in lowered or "no corresponding tool output" in lowered:
            return True
        if re.search(
            r"expected\s+\d+\s+(?:tool(?:-use)?\s*)?(?:calls?|steps?)", lowered
        ) and re.search(r"\b(?:has|contains|uses)\s+\d+\b", lowered):
            return True

        immutable_markers = [
            "does not accomplish the user",
            "never creates",
            "no tool call performs",
            "no call performs",
            "never writes",
        ]
        return any(marker in lowered for marker in immutable_markers)

    def _heuristic_trajectory_check(
        self,
        messages: List[Dict[str, Any]],
        required_tool_steps: int,
        task_type: str,
        reference_answer: str,
        problem: str = "",
        ordered_tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[bool, str]:
        if not messages:
            return False, "empty trajectory"

        system_count = sum(1 for m in messages if m.get("role") == "system")
        user_positions = [
            idx for idx, m in enumerate(messages) if m.get("role") == "user"
        ]
        if system_count != 1:
            return False, "trajectory must contain exactly one system message"
        if len(user_positions) != 1:
            return False, "trajectory must contain exactly one user message"
        if user_positions[0] != 1:
            return False, "user message must be the second message"

        if any(m.get("role") == "user" for m in messages[user_positions[0] + 1 :]):
            return False, "extra user turns are not allowed in synthesized trajectory"

        actual_tool_steps = sum(
            len(m.get("tool_calls") or [])
            for m in messages
            if m.get("role") == "assistant"
        )
        tool_output_count = sum(1 for m in messages if m.get("role") == "tool")
        if required_tool_steps > 0 and actual_tool_steps != required_tool_steps:
            return (
                False,
                f"tool-step count mismatch ({actual_tool_steps} != {required_tool_steps})",
            )
        if actual_tool_steps > tool_output_count:
            return (
                False,
                f"missing tool outputs ({actual_tool_steps} calls vs {tool_output_count} outputs)",
            )

        if str(task_type).lower() == TaskType.MUTATION.value:
            target_tokens = []
            for token in re.findall(
                r"(?:/[A-Za-z0-9_./-]+|[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8})",
                problem or "",
            ):
                token_norm = token.strip().lower()
                if len(token_norm) < 4:
                    continue
                if token_norm in {"readme", "license"}:
                    continue
                target_tokens.append(token_norm)
            target_tokens = list(dict.fromkeys(target_tokens))[:8]
            if target_tokens:
                tool_args_text_parts: List[str] = []
                for msg in messages:
                    if msg.get("role") != "assistant":
                        continue
                    for tc in msg.get("tool_calls", []) or []:
                        args_raw = tc.get("function", {}).get("arguments", {})
                        tool_args_text_parts.append(self._truncate_text(args_raw).lower())
                tool_args_text = "\n".join(tool_args_text_parts)
                overlap = sum(1 for token in target_tokens if token in tool_args_text)
                if overlap == 0:
                    return (
                        False,
                        "mutation targets from problem are not reflected in tool-call arguments",
                    )

        first_tool_assistant_content = ""
        has_final = False
        covered_tool_steps = 0
        step_thoughts: List[str] = []

        for msg in messages:
            if msg.get("role") == "assistant":
                content = self._strip_reasoning_artifacts(str(msg.get("content", "") or ""))
                lowered = content.lower()
                if "[plan]" in lowered or "[step" in lowered or "[truncated]" in lowered:
                    return False, "trajectory contains formatting markers"
                if msg.get("tool_calls"):
                    if content.strip():
                        covered_tool_steps += len(msg.get("tool_calls") or [])
                        if not first_tool_assistant_content:
                            first_tool_assistant_content = content
                        for line in content.splitlines():
                            cleaned = line.strip()
                            if cleaned:
                                step_thoughts.append(cleaned)
                if content.strip() and not msg.get("tool_calls"):
                    has_final = True

        if self.require_planning_step and required_tool_steps > 0:
            if not first_tool_assistant_content:
                return False, "missing planning/step reasoning before tool calls"
        if self.require_final_answer and not has_final:
            return False, "missing final answer"

        if required_tool_steps > 0:
            coverage = covered_tool_steps / max(1, required_tool_steps)
            if coverage < self.min_step_coverage_ratio:
                return (
                    False,
                    f"step coverage too low ({coverage:.2f} < {self.min_step_coverage_ratio:.2f})",
                )

        if step_thoughts:
            normalized = [
                re.sub(r"\s+", " ", re.sub(r"`[^`]+`", "", t.lower())).strip()
                for t in step_thoughts
            ]
            boilerplate_phrase = fallback_prompts.REPEATED_TEMPLATE_PHRASE
            boilerplate_hits = sum(1 for t in normalized if boilerplate_phrase in t)
            if boilerplate_hits >= 2:
                return False, "reasoning is overly template-like (repeated boilerplate)"

            unique_ratio = len(set(normalized)) / max(1, len(normalized))
            if len(normalized) >= 4 and unique_ratio < 0.45:
                return False, "reasoning diversity is too low across tool-use steps"

            verbose_lines = [t for t in step_thoughts if len(t) > 280]
            if len(verbose_lines) >= 2:
                return False, "reasoning lines are too verbose and likely leaking raw arguments"

        if str(task_type).lower() == TaskType.RETRIEVAL.value:
            final_assistant_text = ""
            for idx in range(len(messages) - 1, -1, -1):
                msg = messages[idx]
                if msg.get("role") == "assistant" and not msg.get("tool_calls"):
                    final_assistant_text = str(msg.get("content", "") or "")
                    break
            if not final_assistant_text.strip():
                return False, "retrieval task missing answer text"
            if reference_answer:
                ref = reference_answer.lower()
                ans = final_assistant_text.lower()
                ref_tokens = [
                    t for t in re.findall(r"[a-z0-9_./-]+", ref) if len(t) >= 3
                ]
                overlap = sum(1 for t in set(ref_tokens) if t in ans)
                if ref_tokens and overlap == 0:
                    return False, "retrieval answer not aligned with reference evidence"

            completeness_ok, completeness_reason = self._check_retrieval_answer_completeness(
                final_answer=final_assistant_text,
                problem=problem,
                reference_answer=reference_answer,
                ordered_tool_calls=ordered_tool_calls or [],
            )
            if not completeness_ok:
                return False, completeness_reason

        return True, "trajectory passes structural heuristic checks"

    @staticmethod
    def _strip_reasoning_artifacts(text: str) -> str:
        if not isinstance(text, str):
            return ""
        cleaned = text.replace("... [truncated]", "...")
        cleaned = re.sub(r"\[Plan\]\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"\[Step\s+\d+\s+Reasoning\]\s*", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def _normalize_messages_for_output(
        self,
        messages: List[Dict[str, Any]],
        problem: str,
        ordered_tool_calls: List[Dict[str, Any]],
        task_type: str,
        reference_answer: str,
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (problem or "").strip()},
        ]

        step_idx = 1
        first_tool_assistant_seen = False

        for msg in messages:
            role = msg.get("role")
            if role == "assistant":
                tool_calls = msg.get("tool_calls") or []
                content = self._strip_reasoning_artifacts(
                    str(msg.get("content", "") or "")
                )
                if tool_calls:
                    if not content:
                        lines: List[str] = []
                        for _ in range(len(tool_calls)):
                            lines.append(
                                self._default_step_thought(step_idx, ordered_tool_calls)
                            )
                            step_idx += 1
                        content = "\n".join(l for l in lines if l).strip()
                    else:
                        step_idx += len(tool_calls)

                    first_tool_assistant_seen = True
                    normalized.append(
                        {
                            "role": "assistant",
                            "content": content,
                            "tool_calls": tool_calls,
                        }
                    )
                else:
                    if content.strip():
                        normalized.append({"role": "assistant", "content": content})

            elif role == "tool":
                tool_msg: Dict[str, Any] = {
                    "role": "tool",
                    "content": self._strip_reasoning_artifacts(
                        str(msg.get("content", "") or "")
                    ),
                }
                if msg.get("tool_call_id"):
                    tool_msg["tool_call_id"] = msg.get("tool_call_id")
                normalized.append(tool_msg)

        has_final = any(
            m.get("role") == "assistant"
            and not m.get("tool_calls")
            and str(m.get("content", "")).strip()
            for m in normalized
        )
        if self.require_final_answer and not has_final:
            normalized.append(
                {
                    "role": "assistant",
                    "content": self._default_final_response(
                        ordered_tool_calls, reference_answer, task_type
                    ),
                }
            )

        return normalized

    def _build_review_record(
        self,
        final_problem: str,
        problem_data: Dict[str, Any],
        traj_data: Dict[str, Any],
        final_messages: List[Dict[str, Any]],
        episode_dir: str,
        source_mode: str,
        quality_tier: str,
        quality_score: float,
        hard_judge_pass: bool,
        soft_judge_pass: bool,
        soft_judge_issues: List[str],
        selected_for_training: bool,
    ) -> Dict[str, Any]:
        task_type = str(problem_data.get("task_type", TaskType.MUTATION.value))
        reference_answer = str(problem_data.get("reference_answer", "") or "")
        tool_calls = self._extract_tool_calls_for_rewrite(traj_data, final_messages)
        normalized_messages = self._normalize_messages_for_output(
            messages=final_messages,
            problem=final_problem,
            ordered_tool_calls=tool_calls,
            task_type=task_type,
            reference_answer=reference_answer,
        )
        sanitized_messages = self._sanitize_messages(normalized_messages, episode_dir)
        sanitized_tool_calls = self._sanitize_content(tool_calls, episode_dir)
        sanitized_problem_data = self._sanitize_content(problem_data, episode_dir)
        sanitized_final_problem = self._sanitize_content(final_problem, episode_dir)
        sanitized_episode_dir = self._sanitize_content(episode_dir, episode_dir)

        return {
            "record_id": str(uuid.uuid4()),
            "episode_dir": sanitized_episode_dir,
            "source_mode": source_mode,
            "mcp_server": sanitized_problem_data.get("mcp_server", "filesystem"),
            "task_type": sanitized_problem_data.get(
                "task_type", TaskType.MUTATION.value
            ),
            "language": sanitized_problem_data.get("language", "en"),
            "problem": sanitized_final_problem,
            "original_problem": sanitized_problem_data.get("problem", ""),
            "context": sanitized_problem_data.get("context", ""),
            "expected_outcome": sanitized_problem_data.get("expected_outcome", ""),
            "reference_answer": sanitized_problem_data.get("reference_answer", ""),
            "tools": sanitized_problem_data.get("tools", []),
            "stage1_candidate_selection": sanitized_problem_data.get(
                "stage1_candidate_selection"
            ),
            "anchor_usage": sanitized_problem_data.get("anchor_usage"),
            "world_context": sanitized_problem_data.get("world_context"),
            "state_evidence": sanitized_problem_data.get("state_evidence"),
            "messages": sanitized_messages,
            "tool_calls": sanitized_tool_calls,
            "quality_tier": str(quality_tier or "reject"),
            "quality_score": float(quality_score or 0.0),
            "hard_judge_pass": bool(hard_judge_pass),
            "soft_judge_pass": bool(soft_judge_pass),
            "soft_judge_issues": list(soft_judge_issues or []),
            "selected_for_training": bool(selected_for_training),
            "statistics": {
                "num_messages": len(sanitized_messages),
                "num_tool_calls": len(sanitized_tool_calls),
                "num_successful_tool_calls": sum(
                    1 for tc in sanitized_tool_calls if tc.get("success", False)
                ),
            },
        }

    def _format_tool_xml(self, tool_call: Dict[str, Any], episode_dir: str) -> str:
        name = tool_call["function"]["name"]
        args = tool_call["function"].get("arguments", {})

        if isinstance(args, str):
            args = self._sanitize_content(args, episode_dir)
            try:
                arg_dict = json.loads(args)
            except Exception:
                arg_dict = {"args": args}
        elif isinstance(args, dict):
            arg_dict = self._sanitize_content(args, episode_dir)
        else:
            arg_dict = {}

        params_str = ""
        for k, v in arg_dict.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            params_str += f"<parameter={k}>\n{v}\n</parameter>\n"

        return f"<tool_call>\n<function={name}>\n{params_str}</function>\n</tool_call>"

    def _format_record(
        self,
        problem: str,
        messages: List[Dict],
        tools: List[Dict],
        episode_dir: str,
    ) -> List[Dict[str, Any]]:
        samples = []
        history = []

        current_instruction = problem
        first_user_message_found = False

        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            content = self._sanitize_content(content, episode_dir)

            if role == "system":
                continue

            if role == "user":
                if not first_user_message_found:
                    current_instruction = problem
                    first_user_message_found = True
                else:
                    current_instruction = content

            elif role == "tool":
                if isinstance(content, (dict, list)):
                    content = json.dumps(content, ensure_ascii=False)
                current_instruction = f"<tool_response>\n{content}\n</tool_response>"

            elif role == "assistant":
                output = ""
                has_tool_calls = bool(m.get("tool_calls"))

                if has_tool_calls:
                    if content:
                        output += f"{content}\n\n"

                    for tc in m["tool_calls"]:
                        output += self._format_tool_xml(tc, episode_dir)
                else:
                    output += content

                sample = {
                    "instruction": current_instruction,
                    "input": "",
                    "output": output,
                    "system": SYSTEM_PROMPT,
                    "history": list(history),
                }
                samples.append(sample)
                history.append([current_instruction, output])

        return samples


def _resolve_output_paths(
    input_dir: str,
    output_file: Optional[str],
    meta_file: Optional[str],
) -> Tuple[str, str]:
    normalized_input = os.path.abspath(input_dir)

    resolved_output = (output_file or "").strip()
    resolved_meta = (meta_file or "").strip()

    if not resolved_output:
        resolved_output = os.path.join(
            normalized_input, "data_synthesis", "synthesized_review_records.json"
        )
    if not resolved_meta:
        resolved_meta = os.path.join(
            normalized_input, "data_synthesis", "synthesis_progress.json"
        )

    return resolved_output, resolved_meta


def _setup_runtime_logging(config_path: str, input_dir: str) -> None:
    try:
        cfg = load_config(config_path)
        level_name = str(getattr(cfg.logging, "level", "INFO")).upper()
        level = getattr(logging, level_name, logging.INFO)
        log_format = getattr(
            cfg.logging,
            "format",
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Try to reduce buffering in non-interactive environments.
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(line_buffering=True)
            if hasattr(sys.stderr, "reconfigure"):
                sys.stderr.reconfigure(line_buffering=True)
        except Exception:
            pass

        handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

        log_file = (getattr(cfg.logging, "file", None) or "").strip()
        if log_file:
            if os.path.isabs(log_file):
                resolved_log_file = log_file
            else:
                resolved_log_file = os.path.join(
                    os.path.abspath(input_dir), "data_synthesis", log_file
                )
            os.makedirs(os.path.dirname(resolved_log_file), exist_ok=True)
            handlers.append(logging.FileHandler(resolved_log_file, encoding="utf-8"))

        logging.basicConfig(
            level=level,
            format=log_format,
            handlers=handlers,
            force=True,
        )
        logger.info("Logging configured (level=%s).", level_name)
        if log_file:
            logger.info("Synthesis log file: %s", resolved_log_file)
        logger.info(
            "If using conda, prefer `conda run --no-capture-output ...` for live streaming logs."
        )
    except Exception:
        logging.basicConfig(level=logging.INFO, force=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="output")
    parser.add_argument(
        "--output",
        default="",
        help=(
            "Output JSON file for synthesized review records. "
            "Default: <input>/data_synthesis/synthesized_review_records.json"
        ),
    )
    parser.add_argument(
        "--meta",
        default="",
        help=(
            "Progress JSON file for resume/skip. "
            "Default: <input>/data_synthesis/synthesis_progress.json"
        ),
    )
    parser.add_argument("--config", default="configs/egts/config.yaml")
    parser.add_argument(
        "--limit", type=int, default=0, help="Max number of episodes to process"
    )
    parser.add_argument(
        "--input-mode",
        choices=[m.value for m in InputMode],
        default=InputMode.AUTO.value,
        help="auto: both raw+synthesized, raw: raw only, synthesized: problem.json only",
    )
    args = parser.parse_args()

    _setup_runtime_logging(args.config, args.input)

    output_file, meta_file = _resolve_output_paths(args.input, args.output, args.meta)
    logging.info("Resolved synthesis output: %s", output_file)
    logging.info("Resolved synthesis meta: %s", meta_file)

    pipeline = DataSynthesisPipeline(args.config)
    asyncio.run(
        pipeline.run(
            args.input,
            output_file,
            meta_file,
            args.limit,
            input_mode=args.input_mode,
        )
    )
