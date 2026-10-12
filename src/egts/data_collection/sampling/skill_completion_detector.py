"""Detects when a model has completed a skill workflow."""

import logging
import re
from typing import List, Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SkillCompletionSignal:
    """Result of skill completion detection."""

    is_completed: bool
    reason: str  # "marker_found", "tool_threshold_met", "checkpoints_and_threshold_met", "max_steps_reached", "not_completed"
    skill_tool_calls: int  # Number of tool calls using skill's tools
    checkpoint_results: List[Dict[str, Any]]
    step_adherence: Optional[float] = None  # 0.0-1.0, fraction of expected steps whose tools were used
    step_adherence_detail: List[Dict[str, Any]] = field(default_factory=list)


class SkillCompletionDetector:
    """Detects when a skill workflow has been completed."""

    def __init__(self, max_steps_per_skill: int = 15):
        """Initialize detector.

        Args:
            max_steps_per_skill: Maximum turns before forcing completion
        """
        self.max_steps_per_skill = max_steps_per_skill

    def check_completion(
        self,
        skill_id: str,
        skill_tools: List[str],
        tool_calls_range: tuple,
        trajectory: Any,  # Trajectory object
        last_assistant_message: str,
        steps_since_skill_start: int,
        skill_start_tool_index: int = 0,
        required_checkpoints: List[Dict[str, Any]] = None,
        step_tools: Optional[List[str]] = None,
    ) -> SkillCompletionSignal:
        """Check if skill has been completed.

        Args:
            skill_id: Current skill ID
            skill_tools: List of tool names for this skill
            tool_calls_range: (min, max) expected tool calls
            trajectory: Current trajectory object
            last_assistant_message: Last assistant message content
            steps_since_skill_start: Number of turns since skill was exposed
            skill_start_tool_index: Index in trajectory.tool_calls where current skill started
            required_checkpoints: List of {"tool": str, "min_count": int} dicts
            step_tools: Optional ordered list of tools expected by each workflow step
                        (extracted from SKILL.md step directives). Used for soft
                        adherence scoring, NOT as a hard completion gate.

        Returns:
            SkillCompletionSignal indicating completion status
        """
        if required_checkpoints is None:
            required_checkpoints = []

        skill_tool_calls = self._count_skill_tool_calls(
            trajectory, skill_tools, skill_start_tool_index
        )
        checkpoint_results = self._check_required_checkpoints(
            trajectory, required_checkpoints, skill_start_tool_index
        )
        all_checkpoints_met = all(r["met"] for r in checkpoint_results)

        # Compute step adherence (soft quality signal, not a hard gate)
        step_adherence = None
        step_adherence_detail: List[Dict[str, Any]] = []
        if step_tools:
            step_adherence, step_adherence_detail = self._compute_step_adherence(
                trajectory, step_tools, skill_start_tool_index
            )

        # Signal 1: Explicit marker
        marker = f"[SKILL_COMPLETED: {skill_id}]"
        if marker in last_assistant_message:
            logger.info(
                f"Skill {skill_id} completed: marker found "
                f"(step_adherence={step_adherence})"
            )
            return SkillCompletionSignal(
                is_completed=True,
                reason="marker_found",
                skill_tool_calls=skill_tool_calls,
                checkpoint_results=checkpoint_results,
                step_adherence=step_adherence,
                step_adherence_detail=step_adherence_detail,
            )

        # Signal 2: Tool threshold + checkpoint validation
        min_expected = tool_calls_range[0]
        if skill_tool_calls >= min_expected:
            if not required_checkpoints or all_checkpoints_met:
                reason = (
                    "checkpoints_and_threshold_met"
                    if required_checkpoints
                    else "tool_threshold_met"
                )
                logger.info(
                    f"Skill {skill_id} completed: {reason} "
                    f"({skill_tool_calls} calls, threshold: {min_expected}, "
                    f"step_adherence={step_adherence})"
                )
                return SkillCompletionSignal(
                    is_completed=True,
                    reason=reason,
                    skill_tool_calls=skill_tool_calls,
                    checkpoint_results=checkpoint_results,
                    step_adherence=step_adherence,
                    step_adherence_detail=step_adherence_detail,
                )
            else:
                # Threshold met but checkpoints not satisfied — keep going
                unmet = [r for r in checkpoint_results if not r["met"]]
                logger.debug(
                    f"Skill {skill_id}: tool threshold met ({skill_tool_calls}) "
                    f"but {len(unmet)} checkpoint(s) unmet: "
                    + ", ".join(
                        f"{r['tool']}({r['actual']}/{r['required']})" for r in unmet
                    )
                )

        # Fallback: Max steps reached
        if steps_since_skill_start >= self.max_steps_per_skill:
            logger.warning(
                f"Skill {skill_id} forced completion: max steps "
                f"({self.max_steps_per_skill}) reached "
                f"(step_adherence={step_adherence})"
            )
            return SkillCompletionSignal(
                is_completed=True,
                reason="max_steps_reached",
                skill_tool_calls=skill_tool_calls,
                checkpoint_results=checkpoint_results,
                step_adherence=step_adherence,
                step_adherence_detail=step_adherence_detail,
            )

        # Not completed yet
        return SkillCompletionSignal(
            is_completed=False,
            reason="not_completed",
            skill_tool_calls=skill_tool_calls,
            checkpoint_results=checkpoint_results,
            step_adherence=step_adherence,
            step_adherence_detail=step_adherence_detail,
        )

    def _count_skill_tool_calls(
        self, trajectory: Any, skill_tools: List[str], start_index: int = 0
    ) -> int:
        """Count successful tool calls using skill's tools since start_index.

        Args:
            trajectory: Trajectory object with tool_calls list (ToolCallRecord dataclass)
            skill_tools: List of tool names for this skill
            start_index: Index in tool_calls to start counting from

        Returns:
            Count of successful tool calls
        """
        count = 0
        skill_tools_set = set(skill_tools)

        for tool_call in trajectory.tool_calls[start_index:]:
            # ToolCallRecord is a dataclass with .success and .tool_name attributes
            if getattr(tool_call, "success", False):
                tool_name = getattr(tool_call, "tool_name", "")
                if tool_name in skill_tools_set:
                    count += 1

        return count

    def _check_required_checkpoints(
        self,
        trajectory: Any,
        required_checkpoints: List[Dict[str, Any]],
        start_index: int = 0,
    ) -> List[Dict[str, Any]]:
        """Check whether required checkpoint tools have been called enough times.

        Supports an ``alternatives`` field: if a checkpoint declares alternative
        tools (e.g. ``{"tool": "get_customer_by_phone", "alternatives":
        ["get_customer_by_name"]}``), calls to ANY of those alternatives count
        toward satisfying the checkpoint.

        Returns a list like:
        [{"tool": "move_file", "required": 2, "actual": 1, "met": False,
          "alternatives_used": 0}, ...]
        """
        if not required_checkpoints:
            return []

        counts: Dict[str, int] = {}
        for tool_call in trajectory.tool_calls[start_index:]:
            if getattr(tool_call, "success", False):
                tool_name = getattr(tool_call, "tool_name", "")
                if tool_name:
                    counts[tool_name] = counts.get(tool_name, 0) + 1

        results = []
        for checkpoint in required_checkpoints:
            tool = str(checkpoint.get("tool", "") or "")
            required = max(1, int(checkpoint.get("min_count", 1) or 1))

            # Count primary tool usage
            actual = counts.get(tool, 0)
            alternatives_used = 0

            # Also count alternative tool usage
            alternatives = checkpoint.get("alternatives", [])
            if isinstance(alternatives, list):
                for alt in alternatives:
                    alt_name = str(alt) if alt else ""
                    if alt_name:
                        alt_count = counts.get(alt_name, 0)
                        actual += alt_count
                        alternatives_used += alt_count

            result = {
                "tool": tool,
                "required": required,
                "actual": actual,
                "met": actual >= required,
            }
            if alternatives:
                result["alternatives_used"] = alternatives_used
                result["alternatives"] = alternatives
            results.append(result)

        return results

    @staticmethod
    def extract_step_tools(skill_workflow_text: str) -> List[str]:
        """Extract ordered tool names from SKILL.md step directives.

        Parses markdown steps of the form::

            ### Step N: Title
            - **Tool**: `tool_name`

        Handles multi-tool steps where a single step references several tools::

            - **Tool**: `tool1`, `tool2`
            - **Tool**: `tool1` or `tool2`
            - **Tool**: `tool1` × 1-n times and `tool2`

        All backtick-enclosed tool names from the Tool line are extracted and
        flattened into the result list in step order. Each step may contribute
        one or more entries.

        Returns an ordered list of tool names from all step directives. Used
        as input to ``_compute_step_adherence`` and ``SkillGuidanceInjector``.
        """
        if not skill_workflow_text:
            return []

        # Match step headers: "### Step N: Title"
        step_pattern = re.compile(r'^###\s+Step\s+\d+', re.MULTILINE)
        step_positions = [m.start() for m in step_pattern.finditer(skill_workflow_text)]

        if not step_positions:
            return []

        # Locate the **Tool**: line in step content, then extract ALL
        # backtick-enclosed names from that line.
        tool_line_pattern = re.compile(r'\*\*Tool\*\*:\s*(.+)')
        tool_name_pattern = re.compile(r'`([^`]+)`')
        step_tools: List[str] = []

        for i, pos in enumerate(step_positions):
            end = step_positions[i + 1] if i + 1 < len(step_positions) else len(skill_workflow_text)
            step_content = skill_workflow_text[pos:end]

            line_match = tool_line_pattern.search(step_content)
            if line_match:
                tool_line = line_match.group(1)
                names = tool_name_pattern.findall(tool_line)
                step_tools.extend(names)

        return step_tools

    def _compute_step_adherence(
        self,
        trajectory: Any,
        step_tools: List[str],
        start_index: int = 0,
    ) -> tuple:
        """Compute how many expected workflow steps had their tools used.

        This is a SOFT quality signal — it does not block completion. A low
        score means the model deviated from the prescribed workflow order.

        Args:
            trajectory: Trajectory object
            step_tools: Ordered list of tools expected per step
            start_index: Tool call index where skill started

        Returns:
            (adherence_score: float 0.0-1.0, detail: List[Dict])
        """
        if not step_tools:
            return None, []

        # Collect tools actually used during this skill
        used_tools: List[str] = []
        for tool_call in trajectory.tool_calls[start_index:]:
            if getattr(tool_call, "success", False):
                tool_name = getattr(tool_call, "tool_name", "")
                if tool_name:
                    used_tools.append(tool_name)

        used_set = set(used_tools)

        # For each step, check if its expected tool appears (anywhere in the skill window)
        detail = []
        matched = 0
        for i, expected_tool in enumerate(step_tools):
            was_used = expected_tool in used_set

            # Find first occurrence position if used
            first_pos = None
            if was_used:
                try:
                    first_pos = used_tools.index(expected_tool)
                except ValueError:
                    pass

            detail.append({
                "step": i + 1,
                "expected_tool": expected_tool,
                "used": was_used,
                "first_use_at_call_index": first_pos,
            })

            if was_used:
                matched += 1

        score = matched / len(step_tools) if step_tools else 1.0
        return score, detail
