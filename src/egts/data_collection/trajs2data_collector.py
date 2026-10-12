"""Strict tool-only trajectory collector for mcp-trajs2data.

This collector enforces that every step must produce a successful tool call.
If the model fails to produce a tool call or the tool execution fails,
the episode is immediately aborted.
"""

import logging
import json
import time
import uuid
import os
import copy
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from pathlib import Path
from datetime import datetime

from .maas_client import MaaSClient
from .utils.config import MaaSConfig
from .mcp_servers.base_server import MCPServerProtocol
from .exploration_state import ExplorationStateRecorder
from prompts import PromptLoader

logger = logging.getLogger(__name__)


# Debug logging - configurable via environment variable
_DEBUG_LOG_ENABLED = os.environ.get("TRAJS2DATA_DEBUG", "").lower() in (
    "1",
    "true",
    "yes",
)
_DEBUG_LOG_PATH = Path(
    os.environ.get("TRAJS2DATA_DEBUG_PATH", "/tmp/trajs2data_debug.log")
)

# Agent log path - configurable via environment variable
_CURSOR_DEBUG_LOG_PATH = Path(
    os.environ.get("CURSOR_DEBUG_LOG_PATH", "/tmp/cursor_debug.log")
)


def _dlog(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Dict[str, Any],
    run_id: str = "run1",
) -> None:
    """Write one NDJSON line to Cursor debug log (no secrets)."""
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        # Ensure directory exists
        if not _CURSOR_DEBUG_LOG_PATH.parent.exists():
            try:
                _CURSOR_DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        with _CURSOR_DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


# endregion agent log


def _dbg(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Dict[str, Any],
    run_id: str = "pre-fix",
) -> None:
    """Debug logging helper - only writes when enabled via environment."""
    if not _DEBUG_LOG_ENABLED:
        return
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


class EpisodeStatus(str, Enum):
    """Status of an episode."""

    SUCCESS = "success"
    ABORTED_NO_TOOL_CALL = "aborted_no_tool_call"
    ABORTED_TOOL_FAILED = "aborted_tool_failed"
    ABORTED_MAX_STEPS = "aborted_max_steps"
    ABORTED_ERROR = "aborted_error"


@dataclass
class ToolCallRecord:
    """Record of a single tool call."""

    tool_name: str
    arguments: Dict[str, Any]
    result: str
    success: bool
    call_id: str
    error_message: Optional[str] = None


@dataclass
class StrictTrajectory:
    """A trajectory collected under strict tool-only constraints."""

    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    tools_used: List[str] = field(default_factory=list)
    num_steps: int = 0  # Number of assistant turns with tool calls
    num_successful_tool_calls: int = (
        0  # Actual count of successful tool calls (PRD's n)
    )
    target_n: int = 0  # Target number of successful tool calls
    status: EpisodeStatus = EpisodeStatus.SUCCESS
    abort_reason: Optional[str] = None
    execution_time: float = 0.0
    model_name: Optional[str] = None
    token_usage: Dict[str, int] = field(
        default_factory=lambda: {"prompt": 0, "completion": 0, "total": 0}
    )
    quality_stats: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if the trajectory is valid (completed successfully with tool calls)."""
        return (
            self.status == EpisodeStatus.SUCCESS and self.num_successful_tool_calls >= 1
        )

    def reached_target(self) -> bool:
        """Check if the trajectory reached its target n."""
        return self.num_successful_tool_calls >= self.target_n

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "messages": self.messages,
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments,
                    "result": tc.result,
                    "success": tc.success,
                    "call_id": tc.call_id,
                    "error_message": tc.error_message,
                }
                for tc in self.tool_calls
            ],
            "tools_used": self.tools_used,
            "num_steps": self.num_steps,
            "num_successful_tool_calls": self.num_successful_tool_calls,
            "target_n": self.target_n,
            "status": self.status.value,
            "abort_reason": self.abort_reason,
            "execution_time": self.execution_time,
            "model_name": self.model_name,
            "token_usage": self.token_usage,
            "quality_stats": self.quality_stats,
        }


class Trajs2DataCollector:
    """Collector for strict tool-only trajectories.

    This collector is designed for the Traj→Problem pipeline where:
    - Every turn must produce at least one tool call
    - All tool calls must execute successfully
    - Any failure immediately aborts the episode
    - Collection stops when target_n successful tool calls is reached
    """

    def __init__(
        self,
        maas_client: MaaSClient,
        maas_config: MaaSConfig,
        strict_mode: bool = True,
        exploration_recorder: Optional[ExplorationStateRecorder] = None,
        read_only_tools: Optional[List[str]] = None,
    ):
        """Initialize the collector.

        Args:
            maas_client: MaaS client for LLM interactions
            maas_config: Configuration for model access
            strict_mode: If True, abort on any failure (default)
            exploration_recorder: Optional recorder for anti-repetition prompting (PRD 4.1.2)
            read_only_tools: List of read-only tools for compression
        """
        self.maas_client = maas_client
        self.maas_config = maas_config
        self.strict_mode = strict_mode
        self.exploration_recorder = exploration_recorder
        self.read_only_tools = (
            set(read_only_tools)
            if read_only_tools
            else {
                "list_directory",
                "read_file",
                "read_text_file",
                "read_multiple_files",
                "get_file_info",
                "directory_tree",
                "search_files",
                "list_allowed_directories",
            }
        )

    async def collect_trajectory(
        self,
        allowed_tools: List[Dict[str, Any]],
        mcp_client: MCPServerProtocol,
        max_steps: int,
        system_prompt: str,
        initial_user_message: Optional[str] = None,
        target_n_tool_calls: Optional[int] = None,
        skill_selections: Optional[List[Any]] = None,
        skill_sampler: Optional[Any] = None,
    ) -> StrictTrajectory:
        """Collect a trajectory with strict tool-call-only enforcement.

        The model is prompted to freely explore using the given tools.
        Every turn must produce a tool call that executes successfully.
        Collection stops when target_n_tool_calls is reached (SUCCESS) or
        max_steps is exceeded without reaching target (ABORTED_MAX_STEPS).

        Args:
            allowed_tools: List of tools the model can use (OpenAI format)
            mcp_client: MCP client for executing tool calls
            max_steps: Maximum number of assistant turns (safety limit)
            system_prompt: System prompt for the model
            initial_user_message: Optional initial user message
            target_n_tool_calls: Target number of successful tool calls (PRD's n).
                                 If None, defaults to max_steps.
            skill_selections: Optional list of SkillSelection objects for sequential exposure
            skill_sampler: Optional SkillSampler instance for loading skill workflows

        Returns:
            StrictTrajectory with collected data and status
        """
        start_time = time.time()

        # Default target_n to max_steps if not specified
        effective_target_n = (
            target_n_tool_calls if target_n_tool_calls is not None else max_steps
        )

        trajectory = StrictTrajectory(target_n=effective_target_n)
        tools_used_set = set()

        # Sequential skill tracking
        current_skill_index = 0
        steps_since_skill_start = 0
        skill_start_tool_index = 0
        skill_completion_detector = None
        skill_completion_log = []  # Track completion events for metadata
        guidance_cache = None

        if skill_selections and skill_sampler:
            from data_collection.sampling.skill_completion_detector import SkillCompletionDetector
            max_steps_per_skill = getattr(
                getattr(skill_sampler, "config", None), "max_steps_per_skill", 15
            )
            skill_completion_detector = SkillCompletionDetector(
                max_steps_per_skill=max_steps_per_skill
            )
            # Pre-compute step tools and raw content for each skill
            step_tools_cache: Dict[str, List[str]] = {}
            for sel in skill_selections:
                try:
                    step_tools_cache[sel.skill_id] = skill_sampler.get_skill_step_tools(
                        sel.skill_id
                    )
                except Exception:
                    step_tools_cache[sel.skill_id] = []

            # Initialize skill guidance cache (off-track detection + progressive nudge)
            guidance_cache = None
            try:
                from data_collection.sampling.skill_guidance import SkillGuidanceCache
                guidance_cache = SkillGuidanceCache()
                for sel in skill_selections:
                    try:
                        step_tools = step_tools_cache.get(sel.skill_id, [])
                        content = skill_sampler.get_skill_content(sel.skill_id)
                        guidance_cache.register(sel.skill_id, step_tools, content)
                    except Exception:
                        pass
            except Exception:
                pass

            logger.info(
                f"Sequential skill mode: {len(skill_selections)} skills to expose "
                f"(max_steps_per_skill={max_steps_per_skill})"
            )

        _dlog(
            "H4",
            "trajs2data_collector.py:collect_trajectory:entry",
            "collector entry",
            {
                "max_steps": max_steps,
                "target_n": effective_target_n,
                "allowed_tools_count": len(allowed_tools),
                "allowed_tool_names": [
                    t.get("name", t.get("function", {}).get("name", ""))
                    for t in allowed_tools
                ][:50],
                "strict_mode": self.strict_mode,
            },
        )

        _dbg(
            "H1",
            "trajs2data_collector.py:collect_trajectory:entry",
            "collector entry",
            {
                "max_steps": max_steps,
                "target_n_tool_calls": effective_target_n,
                "allowed_tools_count": len(allowed_tools),
                "strict_mode": self.strict_mode,
            },
        )

        # Build initial messages
        messages = [{"role": "system", "content": system_prompt}]

        if initial_user_message:
            messages.append({"role": "user", "content": initial_user_message})
        else:
            # Default exploration prompt
            messages.append(
                {
                    "role": "user",
                    "content": self._build_exploration_prompt(allowed_tools),
                }
            )

        trajectory.messages = messages.copy()

        # Convert tools to OpenAI format if needed
        tool_schemas = self._ensure_openai_format(allowed_tools)
        _dbg(
            "H1",
            "trajs2data_collector.py:collect_trajectory:tools",
            "tools prepared",
            {
                "tool_schema_count": len(tool_schemas),
                "tool_names": [t.get("function", {}).get("name") for t in tool_schemas][
                    :20
                ],
            },
        )

        try:
            for step in range(max_steps):
                logger.debug(
                    f"Step {step + 1}/{max_steps}, successful_tool_calls={trajectory.num_successful_tool_calls}/{effective_target_n}"
                )

                # Check if we've reached target before making another LLM call
                if trajectory.num_successful_tool_calls >= effective_target_n:
                    logger.info(
                        f"Reached target n={effective_target_n} successful tool calls, stopping collection"
                    )
                    break

                messages_for_llm = messages.copy()

                # Get LLM response
                try:
                    response = await self.maas_client.generate_completion(
                        messages=messages_for_llm,
                        model_config=self.maas_config.models.trajectory_collection,
                        tools=tool_schemas,
                    )
                except Exception as e:
                    if (
                        self._is_transient_llm_error(e)
                        and trajectory.num_successful_tool_calls >= 1
                    ):
                        trajectory.status = EpisodeStatus.SUCCESS
                        trajectory.abort_reason = (
                            f"Salvaged after transient LLM error: {type(e).__name__}: {e}"
                        )
                        logger.warning(
                            "Transient LLM error after %d successful tool calls; salvaging trajectory. error=%s",
                            trajectory.num_successful_tool_calls,
                            e,
                        )
                        break
                    raise

                usage = response.get("usage", {})
                if usage:
                    trajectory.token_usage["prompt"] += usage.get("prompt_tokens", 0)
                    trajectory.token_usage["completion"] += usage.get(
                        "completion_tokens", 0
                    )
                    trajectory.token_usage["total"] += usage.get("total_tokens", 0)

                # Capture raw response characteristics (no secrets)
                content = response.get("content")
                content_str = str(content) if content is not None else ""
                raw_tool_calls = response.get("tool_calls") or []
                _dbg(
                    "H1",
                    "trajs2data_collector.py:collect_trajectory:llm_response",
                    "llm response received",
                    {
                        "step": step + 1,
                        "finish_reason": response.get("finish_reason"),
                        "has_structured_tool_calls": bool(raw_tool_calls),
                        "structured_tool_calls_count": len(raw_tool_calls)
                        if raw_tool_calls
                        else 0,
                        "content_len": len(content_str),
                        "content_has_tool_call_tag": "<tool_call>" in content_str,
                        "content_has_function_calls_tag": "<function_calls>"
                        in content_str,
                        "content_preview_400": content_str[:400],
                    },
                )

                # Extract model name on first step
                if step == 0:
                    trajectory.model_name = self._extract_model_name(response)

                # Normalize tool calls into OpenAI dict format (compatibility mode)
                raw_tool_calls = response.get("tool_calls") or []
                tool_calls_for_message: List[Dict[str, Any]] = []

                if raw_tool_calls:
                    for tc in raw_tool_calls:
                        if hasattr(tc, "function"):
                            tool_name = tc.function.name
                            args_str = tc.function.arguments
                            call_id = tc.id
                        else:
                            tool_name = tc["function"]["name"]
                            args_str = tc["function"]["arguments"]
                            call_id = tc["id"]

                        tool_calls_for_message.append(
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": args_str,
                                },
                            }
                        )
                elif response.get("content"):
                    # Text-format tool calls embedded in assistant content
                    tool_calls_for_message = self._parse_text_tool_calls(
                        str(response["content"]),
                        tool_schemas,
                    )
                    _dbg(
                        "H2",
                        "trajs2data_collector.py:collect_trajectory:parsed_text_tool_calls",
                        "parsed tool calls from text content",
                        {
                            "step": step + 1,
                            "parsed_count": len(tool_calls_for_message),
                            "parsed_names": [
                                c.get("function", {}).get("name")
                                for c in tool_calls_for_message
                            ][:20],
                        },
                    )

                # Handle no tool call — model may be reasoning, planning, or finished
                if not tool_calls_for_message:
                    finish_reason = response.get("finish_reason", "")
                    if finish_reason == "stop":
                        # Model indicates task is complete — respect it
                        logger.info("Model finished (finish_reason=stop), ending episode")
                        # Add assistant reasoning to messages even without tool calls
                        if response.get("content"):
                            messages.append(self._build_assistant_message(response))
                        break
                    # Model produced reasoning/planning but no tool call — allow it
                    if response.get("content"):
                        logger.debug("Model produced reasoning without tool call, continuing")
                        messages.append(self._build_assistant_message(response))
                        continue
                    # Completely empty response — gentle nudge
                    logger.debug("Empty model response — nudging for tool use")
                    messages.append({
                        "role": "user",
                        "content": "Please use one of the available tools to continue exploring.",
                    })
                    continue

                # Add assistant message BEFORE tool results (OpenAI-style ordering)
                assistant_message = self._build_assistant_message(response)
                messages.append(assistant_message)

                # Track whether this step had any successful tool calls
                step_had_success = False

                # Execute tool calls and append tool results
                for tc in tool_calls_for_message:
                    tool_name = tc["function"]["name"]
                    args_raw = tc["function"]["arguments"]
                    call_id = tc["id"]
                    assistant_message["tool_calls"].append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": args_raw,
                            },
                        }
                    )

                    # Parse arguments (stringified JSON preferred)
                    parse_failed = False
                    arguments: Dict[str, Any] = {}
                    success = False
                    result_content = ""
                    error_message = None
                    try:
                        if isinstance(args_raw, str):
                            args_raw_str = args_raw.strip()
                            arguments = json.loads(args_raw_str) if args_raw_str else {}
                        elif isinstance(args_raw, dict):
                            arguments = args_raw
                    except json.JSONDecodeError as e:
                        parse_failed = True
                        error_message = f"Invalid JSON arguments: {e}"
                        result_content = json.dumps(
                            {"error": error_message}, ensure_ascii=False
                        )
                        logger.warning(
                            f"Tool call parse error: {error_message}"
                        )

                    # Execute tool call
                    if not parse_failed:
                        logger.info(
                            f"Executing: {tool_name}({json.dumps(arguments)[:100]}...)"
                        )

                        try:
                            result = await mcp_client.call_tool(tool_name, arguments)
                            result_content = self._format_tool_result(result)

                            # Check for isError flag in MCP result (non-exception failures)
                            is_error = self._check_mcp_error(result)
                            if is_error:
                                error_message = self._extract_error_message(result)
                                _dlog(
                                    "H4",
                                    "trajs2data_collector.py:call_tool:isError",
                                    "tool returned isError",
                                    {
                                        "tool_name": tool_name,
                                        "arg_keys": list(arguments.keys())[:30],
                                        "error_message": (error_message or "")[:500],
                                    },
                                )
                                logger.warning(
                                    f"Tool {tool_name} returned error: {error_message}"
                                )
                                success = False
                            else:
                                success = True
                                step_had_success = True
                                trajectory.num_successful_tool_calls += 1
                                _dlog(
                                    "H4",
                                    "trajs2data_collector.py:call_tool:success",
                                    "tool call success",
                                    {
                                        "tool_name": tool_name,
                                        "arg_keys": list(arguments.keys())[:30],
                                        "n_actual": trajectory.num_successful_tool_calls,
                                        "n_target": effective_target_n,
                                    },
                                )

                        except Exception as e:
                            error_message = str(e)
                            _dlog(
                                "H4",
                                "trajs2data_collector.py:call_tool:exception",
                                "tool call exception",
                                {
                                    "tool_name": tool_name,
                                    "arg_keys": list(arguments.keys())[:30],
                                    "error_message": (error_message or "")[:800],
                                },
                            )
                            logger.warning(
                                f"Tool {tool_name} failed: {error_message}"
                            )
                            result_content = json.dumps(
                                {"error": error_message}, ensure_ascii=False
                            )
                            success = False

                    # Record tool call
                    trajectory.tool_calls.append(
                        ToolCallRecord(
                            tool_name=tool_name,
                            arguments=arguments,
                            result=result_content,
                            success=success,
                            call_id=call_id,
                            error_message=error_message,
                        )
                    )
                    if success:
                        tools_used_set.add(tool_name)

                    # Add tool result to messages
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": result_content,
                        }
                    )

                    # Check if we've reached target after this tool call
                    if trajectory.num_successful_tool_calls >= effective_target_n:
                        logger.info(
                            f"Reached target n={effective_target_n} during tool execution"
                        )
                        break

                # Increment step count if we had any successful tool calls
                if step_had_success:
                    trajectory.num_steps += 1

                # Sequential skill completion check
                if skill_completion_detector and current_skill_index < len(skill_selections):
                    steps_since_skill_start += 1
                    current_skill = skill_selections[current_skill_index]

                    # Get last assistant message content for marker detection
                    last_assistant_content = ""
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant":
                            last_assistant_content = msg.get("content", "") or ""
                            break

                    completion_signal = skill_completion_detector.check_completion(
                        skill_id=current_skill.skill_id,
                        skill_tools=current_skill.tools,
                        tool_calls_range=current_skill.tool_calls_range,
                        trajectory=trajectory,
                        last_assistant_message=last_assistant_content,
                        steps_since_skill_start=steps_since_skill_start,
                        skill_start_tool_index=skill_start_tool_index,
                        required_checkpoints=current_skill.required_checkpoints,
                        step_tools=step_tools_cache.get(current_skill.skill_id),
                    )

                    if completion_signal.is_completed:
                        unmet_checkpoints = [
                            checkpoint
                            for checkpoint in completion_signal.checkpoint_results
                            if not checkpoint.get("met", False)
                        ]
                        unmet_checkpoint_summary = ", ".join(
                            f"{checkpoint['tool']}({checkpoint['actual']}/{checkpoint['required']})"
                            for checkpoint in unmet_checkpoints
                        )
                        skill_completion_log.append({
                            "skill_id": current_skill.skill_id,
                            "reason": completion_signal.reason,
                            "tool_calls": completion_signal.skill_tool_calls,
                            "steps": steps_since_skill_start,
                            "checkpoint_results": completion_signal.checkpoint_results,
                            "unmet_checkpoints": unmet_checkpoints,
                            "unmet_checkpoint_summary": unmet_checkpoint_summary,
                            "step_adherence": completion_signal.step_adherence,
                            "step_adherence_detail": completion_signal.step_adherence_detail,
                        })
                        logger.info(
                            f"Skill {current_skill.skill_id} completed "
                            f"(reason: {completion_signal.reason}, "
                            f"tool_calls: {completion_signal.skill_tool_calls}, "
                            f"steps: {steps_since_skill_start}, "
                            f"unmet_checkpoints: {unmet_checkpoint_summary or 'none'})"
                        )

                        # Move to next skill
                        current_skill_index += 1
                        steps_since_skill_start = 0
                        skill_start_tool_index = len(trajectory.tool_calls)

                        # Inject next skill if available
                        if current_skill_index < len(skill_selections):
                            next_skill = skill_selections[current_skill_index]
                            try:
                                next_workflow = skill_sampler.load_single_skill_workflow(
                                    next_skill.skill_id, is_first=False
                                )
                                messages.append({
                                    "role": "user",
                                    "content": next_workflow,
                                })
                                logger.info(
                                    f"Injected next skill: {next_skill.skill_id}"
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to load next skill {next_skill.skill_id}: {e}"
                                )
                        else:
                            logger.info("All skills completed")

                    else:
                        # Skill not completed — check for off-track drift and inject guidance
                        if guidance_cache is not None:
                            skill_id = current_skill.skill_id
                            injector = guidance_cache.get(skill_id)
                            if injector is not None:
                                last_tool_name = ""
                                if trajectory.tool_calls:
                                    last_tc = trajectory.tool_calls[-1]
                                    last_tool_name = getattr(last_tc, "tool_name", "") or ""
                                if last_tool_name:
                                    injector.record_step(last_tool_name)
                                    guidance_msg = injector.get_guidance()
                                    if guidance_msg:
                                        messages.append({
                                            "role": "user",
                                            "content": guidance_msg,
                                        })
                                        logger.info(
                                            f"Skill guidance injected for {skill_id} "
                                            f"(off_track: {injector.off_track_count})"
                                        )

                # Check if we've reached target
                if trajectory.num_successful_tool_calls >= effective_target_n:
                    break

                # Check if model wants to stop (finish_reason)
                if (
                    response.get("finish_reason") == "stop"
                    and not tool_calls_for_message
                ):
                    break

            # Final status determination
            if trajectory.status == EpisodeStatus.SUCCESS:
                if trajectory.num_successful_tool_calls >= effective_target_n:
                    # SUCCESS: reached target
                    logger.info(
                        f"Episode SUCCESS: reached target n={effective_target_n}"
                    )
                elif trajectory.num_successful_tool_calls >= 1:
                    # SUCCESS: at least one tool call, didn't hit abort conditions
                    # This is still valid data even if we didn't reach max target
                    logger.info(
                        f"Episode SUCCESS: {trajectory.num_successful_tool_calls} tool calls (target was {effective_target_n})"
                    )
                else:
                    # No successful tool calls at all - this shouldn't happen in strict mode
                    trajectory.status = EpisodeStatus.ABORTED_NO_TOOL_CALL
                    trajectory.abort_reason = "No successful tool calls in episode"

        except Exception as e:
            trajectory.status = EpisodeStatus.ABORTED_ERROR
            trajectory.abort_reason = f"Unexpected error: {str(e)}"
            logger.error(f"Episode aborted with error: {e}", exc_info=True)

        self._drop_trailing_empty_assistant(messages)
        alignment_error = self._validate_message_tool_alignment(trajectory, messages)
        if alignment_error:
            logger.error(
                "Trajectory structural mismatch detected at collect_trajectory finalization: %s",
                alignment_error,
            )
            if trajectory.status == EpisodeStatus.SUCCESS:
                trajectory.status = EpisodeStatus.ABORTED_ERROR
            if trajectory.abort_reason:
                trajectory.abort_reason = (
                    f"{trajectory.abort_reason}; structural_mismatch={alignment_error}"
                )
            else:
                trajectory.abort_reason = (
                    f"Structural mismatch detected: {alignment_error}"
                )

        # Finalize trajectory
        trajectory.messages = messages
        trajectory.tools_used = list(tools_used_set)
        trajectory.execution_time = time.time() - start_time

        # Add skill completion metadata
        if skill_selections:
            trajectory.quality_stats["skills_completed"] = current_skill_index
            trajectory.quality_stats["skills_total"] = len(skill_selections)
            trajectory.quality_stats["skill_completion_log"] = skill_completion_log
            trajectory.quality_stats["skill_guided_complete"] = (
                current_skill_index >= len(skill_selections)
            )

        logger.info(
            f"Trajectory collected: status={trajectory.status.value}, "
            f"successful_tool_calls={trajectory.num_successful_tool_calls}/{effective_target_n}, "
            f"steps={trajectory.num_steps}, tools_used={len(trajectory.tools_used)}"
        )

        return trajectory

    def _check_mcp_error(self, result: Any) -> bool:
        """Check if MCP result indicates an error (isError flag or error in content).

        Args:
            result: MCP tool call result

        Returns:
            True if result indicates an error
        """
        # Check dict-style result
        if isinstance(result, dict):
            if result.get("isError"):
                return True
            # Check content for error indicators
            content = result.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "error":
                        return True
            return False

        # Check object-style result (mcp SDK objects)
        if hasattr(result, "isError") and result.isError:
            return True

        # Check content attribute
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, list):
                for item in content:
                    if hasattr(item, "type") and item.type == "error":
                        return True
                    if isinstance(item, dict) and item.get("type") == "error":
                        return True

        return False

    @staticmethod
    def _is_transient_llm_error(error: Exception) -> bool:
        """Best-effort detection for transient model/API failures (timeout/connection)."""
        err_type = type(error).__name__.lower()
        err_text = str(error).lower()
        markers = [
            "timeout",
            "timed out",
            "connect",
            "connection",
            "read timeout",
            "apierror",
            "apiconnectionerror",
            "ratelimit",
            "temporar",
            "unavailable",
            "failed dependency",
            "max retries exceeded",
        ]
        return any(m in err_type or m in err_text for m in markers)

    def _extract_error_message(self, result: Any) -> str:
        """Extract error message from MCP result.

        Args:
            result: MCP tool call result with error

        Returns:
            Error message string
        """
        # Check dict-style result
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "error":
                            return item.get("text", "Unknown error")
                        if item.get("text"):
                            return item.get("text")
            return str(result.get("error", "Unknown error"))

        # Check object-style result
        if hasattr(result, "content"):
            content = result.content
            if isinstance(content, list):
                for item in content:
                    if hasattr(item, "text"):
                        return item.text
            return str(content)

        return "Unknown error"

    def _build_exploration_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """Build a prompt for free exploration."""
        tool_names = []
        for tool in tools:
            if "function" in tool:
                tool_names.append(tool["function"]["name"])
            elif "name" in tool:
                tool_names.append(tool["name"])

        return PromptLoader().get_exploration_prompt(tool_names=", ".join(tool_names))

    def _ensure_openai_format(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Ensure tools are in OpenAI function calling format."""
        formatted = []
        for tool in tools:
            if "type" in tool and tool["type"] == "function":
                formatted.append(tool)
            elif "name" in tool and "description" in tool:
                # Convert from MCP format
                formatted.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool.get("inputSchema", {}),
                        },
                    }
                )
            else:
                formatted.append(tool)
        return formatted

    def _extract_model_name(self, response: Dict[str, Any]) -> Optional[str]:
        """Extract model name from response."""
        if "raw_response" in response:
            raw = response["raw_response"]
            if hasattr(raw, "model"):
                return raw.model
        return self.maas_config.models.trajectory_collection.model

    def _parse_text_tool_calls(
        self, content: str, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Parse tool calls from text content (compatibility mode).

        Supports common formats produced by some models when tool_calls is not
        populated in the API response:
        - <tool_call>tool_name</tool_call>
        - <tool_call>tool_name({...json...})</tool_call>
        - <tool_call>{"name": "...", "arguments": {...}}</tool_call>
        - <function_calls><invoke name="..."><parameter name="...">...</parameter></invoke>...</function_calls>
        """
        import re

        if not content:
            return []

        tool_calls: List[Dict[str, Any]] = []
        tool_name_map = {t["function"]["name"]: t for t in tools if "function" in t}

        def _add_call(tool_name: str, arguments: Any):
            if not tool_name:
                return
            if tool_name not in tool_name_map:
                _dbg(
                    "H2",
                    "trajs2data_collector.py:_parse_text_tool_calls:unknown_tool",
                    "ignored unknown tool name from text",
                    {
                        "tool_name": tool_name,
                        "known_tools": list(tool_name_map.keys())[:50],
                    },
                )
                logger.debug(f"Ignored unknown tool name in text format: {tool_name}")
                return

            call_id = f"call_{uuid.uuid4().hex[:8]}"
            if isinstance(arguments, str):
                args_str = arguments
            else:
                args_str = json.dumps(arguments or {}, ensure_ascii=False)

            tool_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": args_str,
                    },
                }
            )

        # Pattern 1: <tool_call>...</tool_call>
        matches = re.findall(r"<tool_call>(.*?)</tool_call>", content, re.DOTALL)
        _dbg(
            "H2",
            "trajs2data_collector.py:_parse_text_tool_calls:matches",
            "tool_call tag matches",
            {
                "matches_count": len(matches),
                "matches_preview": [(m or "").strip()[:160] for m in matches[:3]],
            },
        )

        for match in matches:
            blob = (match or "").strip()
            if not blob:
                continue

            # 0) XML-ish arg_key/arg_value pairs:
            # <tool_call>search_files<arg_key>path</arg_key><arg_value>.</arg_value>...</tool_call>
            # Some models emit this format when tool calls aren't supported natively.
            m0 = re.match(r"^(\w+)\s*(.*)$", blob, re.DOTALL)
            if m0:
                tool_name0 = m0.group(1)
                rest0 = (m0.group(2) or "").strip()
                if "<arg_key>" in rest0 and "<arg_value>" in rest0:
                    keys = re.findall(r"<arg_key>(.*?)</arg_key>", rest0, re.DOTALL)
                    vals = re.findall(r"<arg_value>(.*?)</arg_value>", rest0, re.DOTALL)
                    if keys and vals:
                        args: Dict[str, Any] = {}
                        for k, v in zip(keys, vals):
                            k = (k or "").strip()
                            v_raw = (v or "").strip()
                            if not k:
                                continue
                            # Try to coerce JSON-ish values, otherwise keep as string
                            try:
                                if v_raw.startswith("{") or v_raw.startswith("["):
                                    args[k] = json.loads(v_raw)
                                else:
                                    args[k] = v_raw
                            except Exception:
                                args[k] = v_raw

                        _add_call(tool_name0, args)
                        continue

            # 1) JSON object form: {"name": "...", "arguments": {...}}
            if blob.lstrip().startswith("{") and blob.rstrip().endswith("}"):
                try:
                    obj = json.loads(blob)
                except Exception:
                    obj = None

                if isinstance(obj, dict):
                    tool_name = (
                        obj.get("name")
                        or obj.get("tool")
                        or (obj.get("function") or {}).get("name")
                    )
                    arguments = (
                        obj.get("arguments")
                        or (obj.get("function") or {}).get("arguments")
                        or {}
                    )
                    if tool_name:
                        _add_call(tool_name, arguments)
                        continue

            # 2) tool_name(args) form
            func_match = re.match(r"(\w+)\s*\((.*)\)\s*$", blob, re.DOTALL)
            if func_match:
                tool_name = func_match.group(1)
                args_str = func_match.group(2).strip()

                arguments: Any = {}
                if args_str:
                    # JSON first
                    try:
                        arguments = json.loads(args_str)
                    except Exception:
                        # key="value" pairs
                        kv_pairs = re.findall(r'(\w+)\s*=\s*"([^"]*)"', args_str)
                        if not kv_pairs:
                            kv_pairs = re.findall(r"(\w+)\s*=\s*'([^']*)'", args_str)
                        arguments = {k: v for k, v in kv_pairs}

                _add_call(tool_name, arguments)
                continue

            # 3) tool_name + JSON on following lines
            lines = [ln.strip() for ln in blob.splitlines() if ln.strip()]
            if lines:
                first = lines[0]
                rest = "\n".join(lines[1:]).strip()
                if first in tool_name_map:
                    if rest:
                        try:
                            arguments = json.loads(rest)
                        except Exception:
                            arguments = {}
                    else:
                        arguments = {}
                    _add_call(first, arguments)
                    continue

            # 4) tool_name only
            if blob in tool_name_map:
                _add_call(blob, {})

        # Pattern 2: <function_calls>...</function_calls>
        for block in re.findall(
            r"<function_calls>(.*?)</function_calls>", content, re.DOTALL
        ):
            for func_name, func_content in re.findall(
                r'<invoke name="(\w+)">(.*?)</invoke>', block, re.DOTALL
            ):
                param_matches = re.findall(
                    r'<parameter name="(\w+)">(.*?)</parameter>',
                    func_content,
                    re.DOTALL,
                )
                arguments = {name: value.strip() for name, value in param_matches}
                _add_call(func_name, arguments)

        if tool_calls:
            logger.warning(f"Parsed {len(tool_calls)} tool calls from text content")

        return tool_calls

    def _format_tool_result(self, result: Any) -> str:
        """Format tool execution result."""
        if hasattr(result, "content"):
            if isinstance(result.content, list):
                parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        parts.append(item.text)
                    else:
                        parts.append(str(item))
                return "\n".join(parts)
            return str(result.content)
        return (
            json.dumps(result, indent=2)
            if isinstance(result, (dict, list))
            else str(result)
        )

    @staticmethod
    def _drop_trailing_empty_assistant(messages: List[Dict[str, Any]]) -> None:
        """Drop trailing assistant messages that contain neither content nor tool_calls."""
        while messages:
            msg = messages[-1]
            if msg.get("role") != "assistant":
                break
            content = str(msg.get("content", "") or "").strip()
            tool_calls = msg.get("tool_calls") or []
            if content or tool_calls:
                break
            messages.pop()

    @staticmethod
    def _build_assistant_message(response: Dict[str, Any]) -> Dict[str, Any]:
        """Build an assistant message that can be replayed to chat-completion APIs."""
        assistant_message = {
            "role": "assistant",
            "content": response.get("content", "") or "",
            "tool_calls": [],
        }
        reasoning_content = response.get("reasoning_content")
        if reasoning_content:
            assistant_message["reasoning_content"] = reasoning_content
        return assistant_message

    def _validate_message_tool_alignment(
        self, trajectory: StrictTrajectory, messages: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Validate tool-call/output structural consistency."""
        assistant_call_ids: List[str] = []
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            for tc in msg.get("tool_calls", []) or []:
                if not isinstance(tc, dict):
                    continue
                call_id = tc.get("id")
                if call_id:
                    assistant_call_ids.append(str(call_id))

        tool_output_ids: List[str] = []
        for msg in messages:
            if msg.get("role") != "tool":
                continue
            call_id = msg.get("tool_call_id")
            if call_id:
                tool_output_ids.append(str(call_id))

        trajectory_call_ids = [str(tc.call_id) for tc in trajectory.tool_calls if tc.call_id]
        successful_calls = sum(1 for tc in trajectory.tool_calls if tc.success)

        n_missing_call_id = sum(1 for tc in trajectory.tool_calls if not tc.call_id)
        if n_missing_call_id > 0:
            return (
                f"{n_missing_call_id} tool_call record(s) have empty or None call_id"
            )
        if len(set(assistant_call_ids)) != len(assistant_call_ids):
            return "duplicate tool_call ids in assistant messages"
        if len(set(tool_output_ids)) != len(tool_output_ids):
            return "duplicate tool_call_id entries in tool messages"
        if len(assistant_call_ids) != len(tool_output_ids):
            return (
                f"assistant/tool count mismatch: calls={len(assistant_call_ids)} "
                f"outputs={len(tool_output_ids)}"
            )
        if set(assistant_call_ids) != set(tool_output_ids):
            return "assistant/tool id sets are inconsistent"
        if len(trajectory_call_ids) != len(tool_output_ids):
            return (
                f"trajectory/messages count mismatch: trajectory.tool_calls={len(trajectory_call_ids)} "
                f"tool_messages={len(tool_output_ids)}"
            )
        if set(trajectory_call_ids) != set(tool_output_ids):
            return "trajectory.tool_calls ids do not match message ids"
        if successful_calls != trajectory.num_successful_tool_calls:
            return (
                f"num_successful_tool_calls mismatch: field={trajectory.num_successful_tool_calls} "
                f"actual={successful_calls}"
            )
        return None

    def _compress_trajectory(
        self, trajectory: "StrictTrajectory"
    ) -> "StrictTrajectory":
        """Remove redundant consecutive read-only operations (PRD 4.1.1 Conservative Compression).

        This method compresses trajectories by removing consecutive duplicate read-only
        tool calls. For example: [ls, ls, ls, read, ls] -> [ls, read, ls]

        This is particularly useful for salvaged trajectories where the model may have
        made multiple failed attempts with the same read-only operation.

        Args:
            trajectory: The trajectory to compress

        Returns:
            The compressed trajectory (modified in-place)
        """
        if not trajectory.tool_calls:
            return trajectory

        original_tool_calls = list(trajectory.tool_calls)
        original_messages = copy.deepcopy(trajectory.messages)

        compressed_calls = []
        removed_call_ids: set[str] = set()
        prev_tool = None
        prev_args_hash = None
        consecutive_count = 0

        for call in trajectory.tool_calls:
            tool_name = call.tool_name
            # Create a hash of arguments for comparison
            args_hash = (
                hash(json.dumps(call.arguments, sort_keys=True))
                if call.arguments
                else None
            )

            # Check if this is a consecutive duplicate read-only operation
            is_read_only = tool_name in self.read_only_tools
            is_duplicate = tool_name == prev_tool and args_hash == prev_args_hash

            if is_read_only and is_duplicate and str(call.call_id or "").strip():
                consecutive_count += 1
                removed_call_ids.add(str(call.call_id))
                # Skip consecutive duplicates (keep only the first one)
                logger.debug(
                    f"[Compression] Skipping duplicate {tool_name} (consecutive #{consecutive_count})"
                )
                continue
            else:
                # Not a duplicate or not read-only, keep it
                compressed_calls.append(call)
                consecutive_count = 0

            prev_tool = tool_name
            prev_args_hash = args_hash

        original_count = len(trajectory.tool_calls)
        compressed_count = len(compressed_calls)

        if original_count != compressed_count:
            logger.info(
                f"[Compression] Compressed trajectory: {original_count} -> {compressed_count} tool calls"
            )

            # Keep messages synchronized with compressed tool_calls.
            filtered_messages: List[Dict[str, Any]] = []
            for msg in trajectory.messages:
                role = msg.get("role")

                if role == "assistant" and msg.get("tool_calls"):
                    raw_tool_calls = msg.get("tool_calls") or []
                    new_tool_calls = []
                    for tc in raw_tool_calls:
                        call_id = str(tc.get("id", "") or "")
                        if call_id and call_id in removed_call_ids:
                            continue
                        new_tool_calls.append(tc)

                    if not new_tool_calls:
                        continue

                    msg_copy = dict(msg)
                    msg_copy["tool_calls"] = new_tool_calls
                    filtered_messages.append(msg_copy)
                    continue

                if role == "tool":
                    call_id = str(msg.get("tool_call_id", "") or "")
                    if call_id and call_id in removed_call_ids:
                        continue

                filtered_messages.append(msg)

            self._drop_trailing_empty_assistant(filtered_messages)

            trajectory.tool_calls = compressed_calls
            trajectory.messages = filtered_messages
            trajectory.num_successful_tool_calls = sum(
                1 for c in compressed_calls if c.success
            )

            success_call_ids = {
                str(tc.call_id)
                for tc in compressed_calls
                if tc.success and str(tc.call_id or "").strip()
            }
            num_steps = 0
            for msg in filtered_messages:
                if msg.get("role") != "assistant":
                    continue
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    continue
                call_ids = [
                    str(tc.get("id", "") or "")
                    for tc in tool_calls
                    if isinstance(tc, dict)
                ]
                if any(call_id in success_call_ids for call_id in call_ids):
                    num_steps += 1
            trajectory.num_steps = num_steps

            alignment_error = self._validate_message_tool_alignment(
                trajectory, trajectory.messages
            )
            if alignment_error:
                logger.warning(
                    "[Compression] Reverting compression due to structural mismatch: %s",
                    alignment_error,
                )
                trajectory.tool_calls = original_tool_calls
                trajectory.messages = original_messages
                trajectory.num_successful_tool_calls = sum(
                    1 for c in original_tool_calls if c.success
                )

        return trajectory

    @staticmethod
    def _tool_call_failure_profile(tool_calls: List[ToolCallRecord]) -> Dict[str, Any]:
        total = len(tool_calls)
        failed = 0
        per_tool: Dict[str, Dict[str, int]] = {}

        for call in tool_calls:
            tool_name = str(call.tool_name or "unknown")
            stats = per_tool.setdefault(tool_name, {"success": 0, "failed": 0})
            if call.success:
                stats["success"] += 1
            else:
                stats["failed"] += 1
                failed += 1

        failure_rate = (failed / total) if total > 0 else 0.0
        return {
            "total_calls": total,
            "failed_calls": failed,
            "failure_rate": failure_rate,
            "per_tool": per_tool,
        }

    def prune_failure_only_tools(
        self, trajectory: "StrictTrajectory"
    ) -> Tuple["StrictTrajectory", Dict[str, Any]]:
        """Prune tool traces that only contain failures and never succeed.

        Rule:
        - For any tool with failed>0 and success==0, remove all its tool-call traces.
        - Keep failed traces for tools that also have successful calls (error-recovery value).
        """
        raw_profile = self._tool_call_failure_profile(trajectory.tool_calls)
        per_tool = raw_profile.get("per_tool", {})
        tools_to_prune = sorted(
            [
                tool_name
                for tool_name, stats in per_tool.items()
                if int(stats.get("failed", 0)) > 0 and int(stats.get("success", 0)) == 0
            ]
        )

        if not tools_to_prune:
            stats = {
                "raw_total_calls": int(raw_profile.get("total_calls", 0)),
                "raw_failed_calls": int(raw_profile.get("failed_calls", 0)),
                "raw_failure_rate": round(float(raw_profile.get("failure_rate", 0.0)), 6),
                "cleaned_total_calls": int(raw_profile.get("total_calls", 0)),
                "cleaned_failed_calls": int(raw_profile.get("failed_calls", 0)),
                "cleaned_failure_rate": round(float(raw_profile.get("failure_rate", 0.0)), 6),
                "removed_failed_calls_count": 0,
                "removed_failure_only_tools": [],
            }
            trajectory.quality_stats = {**(trajectory.quality_stats or {}), **stats}
            return trajectory, stats

        removed_call_ids = set()
        kept_calls: List[ToolCallRecord] = []
        removed_calls_count = 0

        for call in trajectory.tool_calls:
            if call.tool_name in tools_to_prune:
                removed_calls_count += 1
                if call.call_id:
                    removed_call_ids.add(str(call.call_id))
                continue
            kept_calls.append(call)

        filtered_messages: List[Dict[str, Any]] = []
        removed_assistant_turns = 0
        removed_tool_messages = 0
        removed_assistant_call_refs = 0

        for msg in trajectory.messages:
            role = msg.get("role")
            if role == "assistant" and msg.get("tool_calls"):
                raw_tool_calls = msg.get("tool_calls") or []
                new_tool_calls = []
                for tc in raw_tool_calls:
                    call_id = str(tc.get("id", "") or "")
                    if call_id and call_id in removed_call_ids:
                        removed_assistant_call_refs += 1
                        continue
                    new_tool_calls.append(tc)

                if not new_tool_calls:
                    removed_assistant_turns += 1
                    continue

                msg_copy = dict(msg)
                msg_copy["tool_calls"] = new_tool_calls
                filtered_messages.append(msg_copy)
                continue

            if role == "tool":
                call_id = str(msg.get("tool_call_id", "") or "")
                if call_id and call_id in removed_call_ids:
                    removed_tool_messages += 1
                    continue

            filtered_messages.append(msg)

        self._drop_trailing_empty_assistant(filtered_messages)

        trajectory.tool_calls = kept_calls
        trajectory.messages = filtered_messages
        trajectory.num_successful_tool_calls = sum(1 for tc in kept_calls if tc.success)

        success_call_ids = {
            str(tc.call_id) for tc in kept_calls if tc.success and str(tc.call_id or "").strip()
        }
        num_steps = 0
        for msg in filtered_messages:
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                continue
            call_ids = [str(tc.get("id", "") or "") for tc in tool_calls if isinstance(tc, dict)]
            if any(call_id in success_call_ids for call_id in call_ids):
                num_steps += 1
        trajectory.num_steps = num_steps

        trajectory.tools_used = sorted(
            {tc.tool_name for tc in kept_calls if tc.success and tc.tool_name}
        )

        cleaned_profile = self._tool_call_failure_profile(trajectory.tool_calls)
        stats = {
            "raw_total_calls": int(raw_profile.get("total_calls", 0)),
            "raw_failed_calls": int(raw_profile.get("failed_calls", 0)),
            "raw_failure_rate": round(float(raw_profile.get("failure_rate", 0.0)), 6),
            "cleaned_total_calls": int(cleaned_profile.get("total_calls", 0)),
            "cleaned_failed_calls": int(cleaned_profile.get("failed_calls", 0)),
            "cleaned_failure_rate": round(
                float(cleaned_profile.get("failure_rate", 0.0)), 6
            ),
            "removed_failed_calls_count": int(removed_calls_count),
            "removed_failure_only_tools": tools_to_prune,
            "removed_assistant_turns_count": int(removed_assistant_turns),
            "removed_assistant_tool_call_refs_count": int(removed_assistant_call_refs),
            "removed_tool_messages_count": int(removed_tool_messages),
        }
        trajectory.quality_stats = {**(trajectory.quality_stats or {}), **stats}
        return trajectory, stats

    def rollback_to_last_successful_prefix(
        self, trajectory: "StrictTrajectory"
    ) -> Tuple["StrictTrajectory", Dict[str, Any]]:
        """Trim trailing failed tail and promote trajectory to SUCCESS when safe.

        Use case:
        - Episode ends with ABORTED_TOOL_FAILED / ABORTED_ERROR after valid progress.
        - Keep all history up to the last successful tool call.
        - Remove trailing failed-only tail to avoid wasting retry attempts.
        """
        if trajectory is None:
            return trajectory, {"applied": False, "reason": "trajectory_is_none"}

        original = copy.deepcopy(trajectory)
        total_calls = len(original.tool_calls)
        if total_calls == 0:
            return trajectory, {"applied": False, "reason": "no_tool_calls"}

        success_indexes = [
            idx for idx, tc in enumerate(original.tool_calls) if tc.success
        ]
        if not success_indexes:
            return trajectory, {"applied": False, "reason": "no_successful_tool_calls"}

        last_success_idx = success_indexes[-1]
        removed_tail_count = total_calls - (last_success_idx + 1)

        # Fast path: no failed tail to trim. Promote status only if needed.
        if removed_tail_count <= 0:
            if original.status != EpisodeStatus.SUCCESS:
                original.status = EpisodeStatus.SUCCESS
                original.abort_reason = (
                    f"Promoted to SUCCESS from {trajectory.status.value} "
                    f"(existing successful prefix retained)"
                )
                return original, {
                    "applied": True,
                    "promotion_only": True,
                    "removed_trailing_calls_count": 0,
                    "new_status": original.status.value,
                }
            return trajectory, {"applied": False, "reason": "already_successful"}

        kept_calls = original.tool_calls[: last_success_idx + 1]
        removed_ids = {
            str(tc.call_id or "")
            for tc in original.tool_calls[last_success_idx + 1 :]
            if str(tc.call_id or "").strip()
        }

        filtered_messages: List[Dict[str, Any]] = []
        removed_assistant_turns = 0
        removed_assistant_refs = 0
        removed_tool_messages = 0

        for msg in original.messages:
            role = msg.get("role")

            if role == "assistant" and msg.get("tool_calls"):
                raw_tool_calls = msg.get("tool_calls") or []
                new_tool_calls = []
                for tc in raw_tool_calls:
                    call_id = str(tc.get("id", "") or "")
                    if call_id and call_id in removed_ids:
                        removed_assistant_refs += 1
                        continue
                    new_tool_calls.append(tc)

                if not new_tool_calls:
                    removed_assistant_turns += 1
                    continue

                msg_copy = dict(msg)
                msg_copy["tool_calls"] = new_tool_calls
                filtered_messages.append(msg_copy)
                continue

            if role == "tool":
                call_id = str(msg.get("tool_call_id", "") or "")
                if call_id and call_id in removed_ids:
                    removed_tool_messages += 1
                    continue

            filtered_messages.append(msg)

        self._drop_trailing_empty_assistant(filtered_messages)

        original.tool_calls = kept_calls
        original.messages = filtered_messages
        original.num_successful_tool_calls = sum(1 for tc in kept_calls if tc.success)

        success_call_ids = {
            str(tc.call_id)
            for tc in kept_calls
            if tc.success and str(tc.call_id or "").strip()
        }
        num_steps = 0
        for msg in filtered_messages:
            if msg.get("role") != "assistant":
                continue
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                continue
            call_ids = [
                str(tc.get("id", "") or "")
                for tc in tool_calls
                if isinstance(tc, dict)
            ]
            if any(call_id in success_call_ids for call_id in call_ids):
                num_steps += 1
        original.num_steps = num_steps
        original.tools_used = sorted(
            {
                tc.tool_name
                for tc in kept_calls
                if tc.success and str(tc.tool_name or "").strip()
            }
        )
        original.status = EpisodeStatus.SUCCESS
        original.abort_reason = (
            f"Trimmed trailing failed tail from {trajectory.status.value}: "
            f"removed {removed_tail_count} call(s)"
        )

        alignment_error = self._validate_message_tool_alignment(
            original, filtered_messages
        )
        if alignment_error:
            logger.warning(
                "Rollback-to-success-prefix aborted due to structural mismatch: %s",
                alignment_error,
            )
            return trajectory, {
                "applied": False,
                "reason": "alignment_mismatch_after_trim",
                "alignment_error": alignment_error,
            }

        stats = {
            "applied": True,
            "promotion_only": False,
            "removed_trailing_calls_count": int(removed_tail_count),
            "removed_assistant_turns_count": int(removed_assistant_turns),
            "removed_assistant_tool_call_refs_count": int(removed_assistant_refs),
            "removed_tool_messages_count": int(removed_tool_messages),
            "new_num_successful_tool_calls": int(original.num_successful_tool_calls),
            "new_num_steps": int(original.num_steps),
            "new_status": original.status.value,
        }
        original.quality_stats = {**(original.quality_stats or {}), **stats}
        return original, stats

    async def collect_trajectory_recoverable(
        self,
        allowed_tools: List[Dict[str, Any]],
        mcp_client: MCPServerProtocol,
        max_steps: int,
        system_prompt: str,
        workspace_path: Path,
        initial_user_message: Optional[str] = None,
        target_n_tool_calls: Optional[int] = None,
        max_failures: int = 3,
        max_failures_per_tool: int = 2,
        max_retries_before_rollback: int = 1,
        enable_filesystem_snapshots: bool = True,
        min_salvage_steps: int = 1,
        required_anchors: Optional[List[str]] = None,
        skill_selections: Optional[List[Any]] = None,
        skill_sampler: Optional[Any] = None,
    ) -> Tuple["StrictTrajectory", Dict[str, Any]]:
        """Collect a trajectory with recoverable failure handling.

        Unlike strict mode, this method:
        - Creates checkpoints before each tool call
        - On failure, first tries in-place retries (Level 1, PRD 4.1)
        - After max_retries_before_rollback, rolls back to checkpoint (Level 2)
        - When max_failures is reached, salvages the valid prefix

        Args:
            allowed_tools: List of tools the model can use
            mcp_client: MCP client for executing tool calls
            max_steps: Maximum number of assistant turns
            system_prompt: System prompt for the model
            workspace_path: Path to workspace for filesystem snapshots
            initial_user_message: Optional initial user message
            target_n_tool_calls: Target number of successful tool calls
            max_failures: Maximum failures before salvaging
            max_failures_per_tool: Max failures per tool before skipping
            max_retries_before_rollback: Level 1 in-place retries before rollback (PRD 4.1)
            enable_filesystem_snapshots: Whether to snapshot filesystem
            min_salvage_steps: Minimum successful steps required for salvage
            required_anchors: List of anchor tools (at least one must be present for salvage)

        Returns:
            Tuple of (StrictTrajectory, checkpoint_stats dict)
        """
        from .state.checkpoint_manager import CheckpointManager, CheckpointType

        start_time = time.time()
        effective_target_n = (
            target_n_tool_calls if target_n_tool_calls is not None else max_steps
        )

        trajectory = StrictTrajectory(target_n=effective_target_n)
        tools_used_set = set()

        # Sequential skill tracking
        current_skill_index = 0
        steps_since_skill_start = 0
        skill_start_tool_index = 0
        skill_completion_detector = None
        skill_completion_log = []
        guidance_cache = None

        if skill_selections and skill_sampler:
            from data_collection.sampling.skill_completion_detector import SkillCompletionDetector
            max_steps_per_skill = getattr(
                getattr(skill_sampler, "config", None), "max_steps_per_skill", 15
            )
            skill_completion_detector = SkillCompletionDetector(
                max_steps_per_skill=max_steps_per_skill
            )
            # Pre-compute step tools and raw content for each skill
            step_tools_cache: Dict[str, List[str]] = {}
            for sel in skill_selections:
                try:
                    step_tools_cache[sel.skill_id] = skill_sampler.get_skill_step_tools(
                        sel.skill_id
                    )
                except Exception:
                    step_tools_cache[sel.skill_id] = []

            # Initialize skill guidance cache (off-track detection + progressive nudge)
            guidance_cache = None
            try:
                from data_collection.sampling.skill_guidance import SkillGuidanceCache
                guidance_cache = SkillGuidanceCache()
                for sel in skill_selections:
                    try:
                        step_tools = step_tools_cache.get(sel.skill_id, [])
                        content = skill_sampler.get_skill_content(sel.skill_id)
                        guidance_cache.register(sel.skill_id, step_tools, content)
                    except Exception:
                        pass
            except Exception:
                pass

            logger.info(
                f"[Recoverable] Sequential skill mode: {len(skill_selections)} skills "
                f"(max_steps_per_skill={max_steps_per_skill})"
            )

        # Initialize checkpoint manager
        checkpoint_manager = CheckpointManager(
            workspace_path=workspace_path,
            mcp_client=mcp_client,
            max_failures=max_failures,
            max_failures_per_tool=max_failures_per_tool,
            enable_filesystem_snapshots=enable_filesystem_snapshots,
        )

        # Build initial messages
        messages = [{"role": "system", "content": system_prompt}]

        if initial_user_message:
            messages.append({"role": "user", "content": initial_user_message})
        else:
            messages.append(
                {
                    "role": "user",
                    "content": self._build_exploration_prompt(allowed_tools),
                }
            )

        trajectory.messages = messages.copy()
        tool_schemas = self._ensure_openai_format(allowed_tools)

        # Track consecutive failures for Level 1 retry logic
        consecutive_step_failures = 0

        # Create initial checkpoint
        await checkpoint_manager.create_checkpoint(
            messages=messages,
            num_successful_tool_calls=0,
            num_steps=0,
            tools_used=[],
            tool_calls_count=0,
            checkpoint_type=CheckpointType.PRE_TOOL_CALL,
        )

        try:
            for step in range(max_steps):
                logger.debug(
                    f"[Recoverable] Step {step + 1}/{max_steps}, "
                    f"successes={trajectory.num_successful_tool_calls}/{effective_target_n}, "
                    f"failures={checkpoint_manager.total_failures}/{max_failures}"
                )

                # Check if we've reached target
                if trajectory.num_successful_tool_calls >= effective_target_n:
                    logger.info(
                        f"Reached target n={effective_target_n} successful tool calls"
                    )
                    break

                # Check if we should salvage
                if checkpoint_manager.should_salvage:
                    logger.warning(
                        f"Max failures ({max_failures}) reached, salvaging..."
                    )
                    best_checkpoint = checkpoint_manager.get_latest_valid_state(
                        min_tools=min_salvage_steps, required_anchors=required_anchors
                    )
                    if best_checkpoint:
                        # Restore to best checkpoint
                        checkpoint_manager.rollback_to_checkpoint(
                            best_checkpoint.checkpoint_id
                        )
                        messages = copy.deepcopy(best_checkpoint.messages)
                        trajectory.num_successful_tool_calls = (
                            best_checkpoint.num_successful_tool_calls
                        )
                        trajectory.num_steps = best_checkpoint.num_steps
                        trajectory.tool_calls = trajectory.tool_calls[
                            : best_checkpoint.tool_calls_count
                        ]
                        tools_used_set = set(best_checkpoint.tools_used)
                        trajectory.status = (
                            EpisodeStatus.SUCCESS
                        )  # Mark as salvaged success
                        trajectory.abort_reason = (
                            f"Salvaged after {max_failures} failures"
                        )
                    else:
                        trajectory.status = EpisodeStatus.ABORTED_TOOL_FAILED
                        trajectory.abort_reason = (
                            f"Max failures reached, no valid checkpoint to salvage"
                        )
                    break

                # Get LLM response
                try:
                    response = await self.maas_client.generate_completion(
                        messages=messages,
                        model_config=self.maas_config.models.trajectory_collection,
                        tools=tool_schemas,
                    )
                except Exception as e:
                    if self._is_transient_llm_error(e):
                        best_checkpoint = checkpoint_manager.get_latest_valid_state(
                            min_tools=min_salvage_steps,
                            required_anchors=required_anchors,
                        )
                        if best_checkpoint:
                            checkpoint_manager.rollback_to_checkpoint(
                                best_checkpoint.checkpoint_id
                            )
                            messages = copy.deepcopy(best_checkpoint.messages)
                            trajectory.num_successful_tool_calls = (
                                best_checkpoint.num_successful_tool_calls
                            )
                            trajectory.num_steps = best_checkpoint.num_steps
                            trajectory.tool_calls = trajectory.tool_calls[
                                : best_checkpoint.tool_calls_count
                            ]
                            tools_used_set = set(best_checkpoint.tools_used)
                            trajectory.status = EpisodeStatus.SUCCESS
                            trajectory.abort_reason = (
                                "Salvaged after transient LLM error "
                                f"(checkpoint): {type(e).__name__}: {e}"
                            )
                            logger.warning(
                                "[Recoverable] Transient LLM error; salvaged from checkpoint with %d successful calls. error=%s",
                                trajectory.num_successful_tool_calls,
                                e,
                            )
                            break
                        if trajectory.num_successful_tool_calls >= min_salvage_steps:
                            trajectory.status = EpisodeStatus.SUCCESS
                            trajectory.abort_reason = (
                                "Salvaged after transient LLM error "
                                f"(in-memory): {type(e).__name__}: {e}"
                            )
                            logger.warning(
                                "[Recoverable] Transient LLM error; salvaged in-memory with %d successful calls. error=%s",
                                trajectory.num_successful_tool_calls,
                                e,
                            )
                            break
                    raise

                usage = response.get("usage", {})
                if usage:
                    trajectory.token_usage["prompt"] += usage.get("prompt_tokens", 0)
                    trajectory.token_usage["completion"] += usage.get(
                        "completion_tokens", 0
                    )
                    trajectory.token_usage["total"] += usage.get("total_tokens", 0)

                if step == 0:
                    trajectory.model_name = self._extract_model_name(response)

                # Extract tool calls
                raw_tool_calls = response.get("tool_calls") or []
                tool_calls_for_message: List[Dict[str, Any]] = []

                if raw_tool_calls:
                    for tc in raw_tool_calls:
                        if hasattr(tc, "function"):
                            tool_name = tc.function.name
                            args_str = tc.function.arguments
                            call_id = tc.id
                        else:
                            tool_name = tc["function"]["name"]
                            args_str = tc["function"]["arguments"]
                            call_id = tc["id"]

                        tool_calls_for_message.append(
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {"name": tool_name, "arguments": args_str},
                            }
                        )
                elif response.get("content"):
                    tool_calls_for_message = self._parse_text_tool_calls(
                        str(response["content"]), tool_schemas
                    )

                # Handle no tool call - record failure and continue
                if not tool_calls_for_message:
                    checkpoint_manager.record_failure(
                        tool_name="none",
                        error_type="no_tool_call",
                        error_message=f"No tool call at step {step + 1}",
                        at_step=step,
                    )

                    # Add a nudge message to encourage tool use
                    messages.append(
                        {
                            "role": "user",
                            "content": "Please use one of the available tools to continue the task.",
                        }
                    )
                    continue

                # Create checkpoint before tool execution (moved inside loop)
                # checkpoint_manager.create_checkpoint(...) - MOVED

                # Add assistant message
                assistant_message = self._build_assistant_message(response)
                messages.append(assistant_message)

                step_had_success = False
                step_failed = False
                step_rolled_back = False

                # Flag to stop processing subsequent tools in this turn if one fails
                abort_turn = False

                # Execute tool calls
                for tc in tool_calls_for_message:
                    if abort_turn:
                        break

                    tool_name = tc["function"]["name"]
                    args_raw = tc["function"]["arguments"]
                    call_id = tc["id"]

                    # Skip tools that have failed too many times
                    if checkpoint_manager.should_skip_tool(tool_name):
                        logger.info(
                            f"Skipping tool {tool_name} due to too many failures"
                        )
                        continue

                    # Create checkpoint before EACH tool execution for granular recovery
                    # This ensures we can rollback this specific tool call without losing previous successes in the same turn
                    current_cp = await checkpoint_manager.create_checkpoint(
                        messages=messages,
                        num_successful_tool_calls=trajectory.num_successful_tool_calls,
                        num_steps=trajectory.num_steps,
                        tools_used=list(tools_used_set),
                        tool_calls_count=len(trajectory.tool_calls),
                        checkpoint_type=CheckpointType.PRE_TOOL_CALL,
                    )

                    assistant_message["tool_calls"].append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": tool_name, "arguments": args_raw},
                        }
                    )

                    arguments = {}
                    success = False
                    result_content = ""
                    error_message = None
                    parse_failed = False

                    # Parse arguments
                    try:
                        if isinstance(args_raw, str):
                            arguments = (
                                json.loads(args_raw.strip()) if args_raw.strip() else {}
                            )
                        elif isinstance(args_raw, dict):
                            arguments = args_raw
                    except json.JSONDecodeError as e:
                        error_message = f"Invalid JSON arguments: {str(e)}"
                        checkpoint_manager.record_failure(
                            tool_name=tool_name,
                            error_type="invalid_args",
                            error_message=error_message,
                            at_step=step,
                        )
                        result_content = json.dumps(
                            {"error": error_message}, ensure_ascii=False
                        )
                        parse_failed = True
                        step_failed = True
                        abort_turn = True

                    # Execute tool call if no parse error
                    if not parse_failed:
                        try:
                            result = await mcp_client.call_tool(tool_name, arguments)
                            result_content = self._format_tool_result(result)

                            is_error = self._check_mcp_error(result)
                            if is_error:
                                error_message = self._extract_error_message(result)
                                checkpoint_manager.record_failure(
                                    tool_name=tool_name,
                                    error_type="execution_error",
                                    error_message=error_message,
                                    at_step=step,
                                )
                                step_failed = True
                                abort_turn = True
                            else:
                                success = True
                                step_had_success = True
                                trajectory.num_successful_tool_calls += 1

                        except Exception as e:
                            error_message = str(e)
                            checkpoint_manager.record_failure(
                                tool_name=tool_name,
                                error_type="exception",
                                error_message=error_message,
                                at_step=step,
                            )
                            result_content = json.dumps(
                                {"error": error_message}, ensure_ascii=False
                            )
                            step_failed = True
                            abort_turn = True

                    # Record tool call (even if failed, unless we rollback)
                    trajectory.tool_calls.append(
                        ToolCallRecord(
                            tool_name=tool_name,
                            arguments=arguments,
                            result=result_content,
                            success=success,
                            call_id=call_id,
                            error_message=error_message,
                        )
                    )

                    if success:
                        tools_used_set.add(tool_name)

                    # Add tool result to messages
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": result_content,
                        }
                    )

                    # Check if target reached
                    if trajectory.num_successful_tool_calls >= effective_target_n:
                        break

                    # Failure Handling (Rollback or Retry)
                    if step_failed:
                        # Track consecutive failures
                        consecutive_step_failures += 1

                        if (
                            consecutive_step_failures
                            > max_retries_before_rollback
                        ):
                            # Level 2: Immediate Rollback to PRE-TOOL checkpoint
                            logger.info(
                                f"[Recoverable] Level 2: Rolling back immediate tool failure ({consecutive_step_failures} failures)"
                            )
                            consecutive_step_failures = 0
                            last_checkpoint = checkpoint_manager.rollback_to_checkpoint(
                                current_cp.checkpoint_id
                            )
                            if last_checkpoint:
                                messages = copy.deepcopy(last_checkpoint.messages)
                                # CRITICAL: Reset trajectory state to match checkpoint
                                # This ensures "ghost" attempts are removed from history
                                trajectory.num_successful_tool_calls = (
                                    last_checkpoint.num_successful_tool_calls
                                )
                                trajectory.num_steps = last_checkpoint.num_steps
                                trajectory.tool_calls = trajectory.tool_calls[
                                    : last_checkpoint.tool_calls_count
                                ]
                                # Rebuild tools_used set from remaining calls
                                tools_used_set = {
                                    tc.tool_name
                                    for tc in trajectory.tool_calls
                                    if tc.success
                                }
                                step_rolled_back = True

                                # Break loop to get new generation from LLM (state is reset)
                                break
                        else:
                            # Level 1: Keep failure in context for Retry
                            # Break loop to stop processing further tools in this turn, ask for fix
                            pass

                # If step had failures but also successes, continue
                # If step had only failures, try in-place retry (Level 1) before rollback (Level 2)
                # MODIFIED: Logic handled inside tool loop for granular rollback
                # But we still need to handle the "Retry Nudge" if we didn't rollback

                if step_failed and consecutive_step_failures > 0:
                    # We did NOT rollback (Level 1), so we need to prompt retry
                    logger.info(
                        f"[Recoverable] Level 1: In-place retry {consecutive_step_failures}/{max_retries_before_rollback}"
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "The previous action failed. Please analyze the error and try a different approach.",
                        }
                    )
                else:
                    # Success or Rolled back (counter reset)
                    consecutive_step_failures = 0

                if step_had_success and not step_rolled_back:
                    trajectory.num_steps += 1

                # Sequential skill completion check
                if skill_completion_detector and current_skill_index < len(skill_selections):
                    steps_since_skill_start += 1
                    current_skill = skill_selections[current_skill_index]

                    last_assistant_content = ""
                    for msg in reversed(messages):
                        if msg.get("role") == "assistant":
                            last_assistant_content = msg.get("content", "") or ""
                            break

                    completion_signal = skill_completion_detector.check_completion(
                        skill_id=current_skill.skill_id,
                        skill_tools=current_skill.tools,
                        tool_calls_range=current_skill.tool_calls_range,
                        trajectory=trajectory,
                        last_assistant_message=last_assistant_content,
                        steps_since_skill_start=steps_since_skill_start,
                        skill_start_tool_index=skill_start_tool_index,
                        required_checkpoints=current_skill.required_checkpoints,
                        step_tools=step_tools_cache.get(current_skill.skill_id),
                    )

                    if completion_signal.is_completed:
                        unmet_checkpoints = [
                            checkpoint
                            for checkpoint in completion_signal.checkpoint_results
                            if not checkpoint.get("met", False)
                        ]
                        unmet_checkpoint_summary = ", ".join(
                            f"{checkpoint['tool']}({checkpoint['actual']}/{checkpoint['required']})"
                            for checkpoint in unmet_checkpoints
                        )
                        skill_completion_log.append({
                            "skill_id": current_skill.skill_id,
                            "reason": completion_signal.reason,
                            "tool_calls": completion_signal.skill_tool_calls,
                            "steps": steps_since_skill_start,
                            "checkpoint_results": completion_signal.checkpoint_results,
                            "unmet_checkpoints": unmet_checkpoints,
                            "unmet_checkpoint_summary": unmet_checkpoint_summary,
                            "step_adherence": completion_signal.step_adherence,
                            "step_adherence_detail": completion_signal.step_adherence_detail,
                        })
                        logger.info(
                            f"[Recoverable] Skill {current_skill.skill_id} completed "
                            f"(reason: {completion_signal.reason}, "
                            f"tool_calls: {completion_signal.skill_tool_calls}, "
                            f"steps: {steps_since_skill_start}, "
                            f"unmet_checkpoints: {unmet_checkpoint_summary or 'none'})"
                        )

                        current_skill_index += 1
                        steps_since_skill_start = 0
                        skill_start_tool_index = len(trajectory.tool_calls)

                        if current_skill_index < len(skill_selections):
                            next_skill = skill_selections[current_skill_index]
                            try:
                                next_workflow = skill_sampler.load_single_skill_workflow(
                                    next_skill.skill_id, is_first=False
                                )
                                messages.append({
                                    "role": "user",
                                    "content": next_workflow,
                                })
                                logger.info(
                                    f"[Recoverable] Injected next skill: {next_skill.skill_id}"
                                )
                            except Exception as e:
                                logger.warning(
                                    f"[Recoverable] Failed to load next skill {next_skill.skill_id}: {e}"
                                )
                        else:
                            logger.info("[Recoverable] All skills completed")

                    else:
                        # Skill not completed — check for off-track drift and inject guidance
                        if guidance_cache is not None:
                            skill_id = current_skill.skill_id
                            injector = guidance_cache.get(skill_id)
                            if injector is not None:
                                last_tool_name = ""
                                if trajectory.tool_calls:
                                    last_tc = trajectory.tool_calls[-1]
                                    last_tool_name = getattr(last_tc, "tool_name", "") or ""
                                if last_tool_name:
                                    injector.record_step(last_tool_name)
                                    guidance_msg = injector.get_guidance()
                                    if guidance_msg:
                                        messages.append({
                                            "role": "user",
                                            "content": guidance_msg,
                                        })
                                        logger.info(
                                            f"[Recoverable] Skill guidance injected for {skill_id} "
                                            f"(off_track: {injector.off_track_count})"
                                        )

                # Check target
                if trajectory.num_successful_tool_calls >= effective_target_n:
                    break

            # Final status
            if trajectory.status == EpisodeStatus.SUCCESS:
                if trajectory.num_successful_tool_calls >= effective_target_n:
                    logger.info(
                        f"[Recoverable] SUCCESS: reached target n={effective_target_n}"
                    )
                elif trajectory.num_successful_tool_calls >= 1:
                    logger.info(
                        f"[Recoverable] SUCCESS: {trajectory.num_successful_tool_calls} tool calls"
                    )
                else:
                    trajectory.status = EpisodeStatus.ABORTED_NO_TOOL_CALL
                    trajectory.abort_reason = "No successful tool calls in episode"

        except Exception as e:
            trajectory.status = EpisodeStatus.ABORTED_ERROR
            trajectory.abort_reason = f"Unexpected error: {str(e)}"
            logger.error(f"Episode aborted with error: {e}", exc_info=True)

        finally:
            # Cleanup checkpoint storage
            checkpoint_manager.cleanup()

        self._drop_trailing_empty_assistant(messages)
        alignment_error = self._validate_message_tool_alignment(trajectory, messages)
        if alignment_error:
            logger.error(
                "[Recoverable] Trajectory structural mismatch detected at finalization: %s",
                alignment_error,
            )
            if trajectory.status == EpisodeStatus.SUCCESS:
                trajectory.status = EpisodeStatus.ABORTED_ERROR
            if trajectory.abort_reason:
                trajectory.abort_reason = (
                    f"{trajectory.abort_reason}; structural_mismatch={alignment_error}"
                )
            else:
                trajectory.abort_reason = (
                    f"Structural mismatch detected: {alignment_error}"
                )

        # Finalize trajectory
        trajectory.messages = messages
        trajectory.tools_used = list(tools_used_set)
        trajectory.execution_time = time.time() - start_time

        # Add skill completion metadata
        if skill_selections:
            trajectory.quality_stats["skills_completed"] = current_skill_index
            trajectory.quality_stats["skills_total"] = len(skill_selections)
            trajectory.quality_stats["skill_completion_log"] = skill_completion_log
            trajectory.quality_stats["skill_guided_complete"] = (
                current_skill_index >= len(skill_selections)
            )

        # Apply Conservative Compression for salvaged trajectories (PRD 4.1.1)
        # This removes redundant consecutive read-only operations
        if trajectory.abort_reason and "Salvaged" in trajectory.abort_reason:
            self._compress_trajectory(trajectory)

        checkpoint_stats = checkpoint_manager.get_stats()

        logger.info(
            f"[Recoverable] Trajectory collected: status={trajectory.status.value}, "
            f"successful_tool_calls={trajectory.num_successful_tool_calls}/{effective_target_n}, "
            f"failures={checkpoint_manager.total_failures}, salvaged={'salvaged' in (trajectory.abort_reason or '')}"
        )

        return trajectory, checkpoint_stats


def build_exploration_system_prompt(
    root_dir: str,
    task_hint: Optional[str] = None,
    target_n: Optional[int] = None,
    task_config: Optional[Any] = None,
    skill_workflow: Optional[str] = None,
    world_context_override: Optional[Dict[str, Any]] = None,
    use_task_objective: bool = False,
) -> str:
    """Build a system prompt for free exploration.

    Args:
        root_dir: Root directory for exploration
        task_hint: Optional hint about what kind of task to perform
        target_n: Optional target number of tool calls to guide the model
        task_config: Optional task configuration
        skill_workflow: Optional skill workflow guidance (concatenated SKILL.md content)
        use_task_objective: If True, use the objective-driven prompt variant that
            asks the model to conceive a concrete task from world context first.

    Returns:
        System prompt string
    """
    try:
        task_type = getattr(task_config, "task_type", "executable_world")
        prompt_domain = getattr(task_config, "prompt_domain", None) or task_type
        world_context = {
            "task_type": task_type,
            "prompt_domain": prompt_domain,
            "root_dir": root_dir,
            "primary_server": getattr(task_config, "primary_server", None),
            "output_namespace": getattr(task_config, "output_namespace", None),
        }
        configured_world_context = {}
        task_world_context = getattr(task_config, "world_context", None)
        if isinstance(task_world_context, dict):
            configured_world_context.update(task_world_context)
        elif task_world_context:
            configured_world_context["description"] = str(task_world_context)
        if world_context_override:
            configured_world_context.update(world_context_override)
        if configured_world_context:
            world_context["configured"] = configured_world_context
        world_context_json = json.dumps(world_context, ensure_ascii=False)
        tool_names_str = "the tool schema provided with this request"
        loader = PromptLoader(prompt_domain)
        if use_task_objective:
            full_prompt = loader.get_exploration_prompt_with_objective(
                tool_names=tool_names_str,
                world_context=world_context_json,
            )
        else:
            full_prompt = loader.get_exploration_prompt(
                tool_names=tool_names_str,
                world_context=world_context_json,
            )

        if skill_workflow:
            full_prompt += skill_workflow

        if task_hint:
            full_prompt += f"\n\nTask hint: {task_hint}"

        return full_prompt

    except Exception as e:
        logger.warning(f"Failed to load prompt from factory: {e}")
        # Fallback to inline prompt

        task_type = getattr(task_config, "task_type", "executable_world")
        prompt_domain = getattr(task_config, "prompt_domain", None) or task_type
        base_prompt = PromptLoader(prompt_domain).get_exploration_prompt(
            tool_names="the tool schema provided with this request",
            world_context=json.dumps(
                {
                    "task_type": task_type,
                    "prompt_domain": prompt_domain,
                    "root_dir": root_dir,
                },
                ensure_ascii=False,
            ),
        )

        if target_n:
            base_prompt += f"\n- Try to perform approximately {target_n} meaningful tool operations"

        if skill_workflow:
            base_prompt += skill_workflow

        if task_hint:
            base_prompt += f"\n\nTask hint: {task_hint}"

        return base_prompt
