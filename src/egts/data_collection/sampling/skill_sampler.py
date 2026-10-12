"""Skill-based tool sampling for professional workflow guidance."""

import json
import logging
import random
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Tuple, Set

logger = logging.getLogger(__name__)


@dataclass
class SkillSelection:
    """Represents a selected skill with its metadata."""

    skill_id: str
    description: str
    tools: List[str]
    tool_calls_range: Tuple[int, int]
    required_checkpoints: List[Dict[str, Any]]


class SkillSampler:
    """Samples and manages skill-based exploration workflows.

    Loads skill definitions from skill_tools.json files (supports both flat
    and category-subdirectory layouts), filters skills by tool availability
    in the current episode, and loads SKILL.md workflow documents.

    Tool-based auto-matching:
        A skill is eligible for the current episode if ALL of its required
        tools are available in the episode's live tool set. This means:
        - No config declaration needed for which skills to expose
        - No server-side skill_categories mapping needed
        - Adding a new skill = drop SKILL.md + update skill_tools.json
    """

    def __init__(
        self,
        config: Any,  # SkillGuidedConfig
        project_root: Path,
        all_tools: List[Dict[str, Any]],
        domain: Optional[str] = None,
        coverage_tracker: Any = None,  # Optional CoverageTracker
    ):
        """Initialize skill sampler.

        Args:
            config: SkillGuidedConfig instance
            project_root: Project root directory
            all_tools: All available tools from MCP server
            domain: Optional domain name to resolve {domain} placeholder in skills_dir
            coverage_tracker: Optional CoverageTracker for coverage-weighted skill selection
        """
        self.config = config
        self.project_root = project_root
        self.all_tools = all_tools
        self.domain = domain
        self.coverage_tracker = coverage_tracker

        # Build tool name -> tool dict mapping
        self._tool_map: Dict[str, Dict[str, Any]] = {}
        for tool in all_tools:
            name = tool.get("name") or tool.get("function", {}).get("name", "")
            if name:
                self._tool_map[name] = tool

        self.live_tool_names: Set[str] = set(self._tool_map.keys())

        # Resolve skills_dir with optional {domain} placeholder
        skills_dir_str = config.skills_dir
        if "{domain}" in skills_dir_str and domain:
            skills_dir_str = skills_dir_str.replace("{domain}", domain)
        self.skills_dir = project_root / skills_dir_str

        # Load all skills (flat + subdirectory layouts)
        self.skills: Dict[str, Dict[str, Any]] = {}
        self._load_all_skills()

        if not self.skills:
            raise ValueError(f"No skills found under {self.skills_dir}")

        logger.info(
            f"Loaded {len(self.skills)} total skills from {self.skills_dir}"
        )

    def _load_all_skills(self):
        """Load skills from skills_dir, scanning both root and subdirectories."""
        skills_json_name = self.config.skills_json

        # 1. Try root-level skill_tools.json
        root_json = self.skills_dir / skills_json_name
        if root_json.exists():
            self._load_skills_from_json(root_json, category=None)

        # 2. Scan subdirectories for per-category skill_tools.json
        if self.skills_dir.is_dir():
            for subdir in sorted(self.skills_dir.iterdir()):
                if not subdir.is_dir():
                    continue
                sub_json = subdir / skills_json_name
                if sub_json.exists():
                    self._load_skills_from_json(sub_json, category=subdir.name)

    def _load_skills_from_json(self, json_path: Path, category: Optional[str]):
        """Load skills from a single skill_tools.json file."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {json_path}: {e}")
            return

        for skill in data.get("skills", []):
            skill_id = skill.get("skill_id")
            if not skill_id:
                continue
            if skill_id in self.skills:
                continue  # first-seen wins (root takes priority over subdirs)
            if category:
                skill["_category"] = category
                skill["_skills_dir"] = str(json_path.parent)
            self.skills[skill_id] = skill

        count = len(data.get("skills", []))
        if category:
            logger.debug(f"  Loaded {count} skills from category '{category}'")
        else:
            logger.debug(f"  Loaded {count} skills from root")

    def _get_eligible_skills(self) -> Dict[str, Dict[str, Any]]:
        """Filter skills to only those whose tools are ALL available in the current episode.

        A skill is eligible if every tool in its `tools` list exists in
        self.live_tool_names. This is the core auto-matching logic.
        """
        eligible = {}
        for skill_id, skill_data in self.skills.items():
            required_tools = set(skill_data.get("tools", []))
            if not required_tools:
                continue
            if required_tools.issubset(self.live_tool_names):
                eligible[skill_id] = skill_data

        return eligible

    def sample_skills(
        self, n_skills: int, env_category: Optional[str] = None
    ) -> List[SkillSelection]:
        """Sample N skills from those eligible for the current episode's tools.

        Eligibility is determined automatically: a skill is eligible if ALL
        of its required tools are present in the current live tool set.

        Args:
            n_skills: Number of skills to sample
            env_category: Optional environment category for additional filtering
                         (legacy; tool-based filtering is the primary mechanism)

        Returns:
            List of SkillSelection objects
        """
        # Primary filter: tool availability
        eligible_skills = self._get_eligible_skills()

        if not eligible_skills:
            logger.warning(
                f"No skills eligible for current tool set "
                f"({len(self.live_tool_names)} live tools). "
                f"Checked {len(self.skills)} skills."
            )
            return []

        # Secondary filter: env_category (legacy, optional)
        if env_category:
            category_filtered = {
                skill_id: skill_data
                for skill_id, skill_data in eligible_skills.items()
                if skill_data.get("env_categories") is None
                or env_category in skill_data.get("env_categories", [])
            }
            if category_filtered:
                eligible_skills = category_filtered

        if n_skills > len(eligible_skills):
            logger.warning(
                f"Requested {n_skills} skills but only {len(eligible_skills)} "
                f"eligible. Sampling all eligible skills."
            )
            n_skills = len(eligible_skills)

        # Select skills based on configured strategy
        selection_strategy = getattr(self.config, "skill_selection_strategy", "random")
        if (
            selection_strategy == "coverage_weighted"
            and self.coverage_tracker is not None
        ):
            sampled_ids = self._weighted_skill_sample(
                list(eligible_skills.keys()), n_skills
            )
        else:
            if selection_strategy == "coverage_weighted":
                logger.debug(
                    "coverage_weighted strategy requested but no CoverageTracker "
                    "available — falling back to random skill selection"
                )
            sampled_ids = random.sample(list(eligible_skills.keys()), n_skills)

        selections = []
        for skill_id in sampled_ids:
            skill_data = eligible_skills[skill_id]
            selections.append(
                SkillSelection(
                    skill_id=skill_id,
                    description=skill_data["description"],
                    tools=skill_data["tools"],
                    tool_calls_range=tuple(skill_data["tool_calls_range"]),
                    required_checkpoints=skill_data.get("required_checkpoints", []),
                )
            )

        logger.info(
            f"Sampled {n_skills} skills from {len(eligible_skills)} eligible "
            f"(out of {len(self.skills)} total): {sampled_ids}"
        )
        return selections

    def _weighted_skill_sample(
        self, skill_ids: List[str], n: int
    ) -> List[str]:
        """Sample skills with inverse coverage weighting.

        Skills whose tools have lower average coverage get higher weight,
        ensuring balanced exposure across all skill types.

        Args:
            skill_ids: List of eligible skill IDs
            n: Number of skills to sample

        Returns:
            List of sampled skill IDs
        """
        if n >= len(skill_ids):
            return list(skill_ids)

        # Compute per-skill weight from average tool coverage
        skill_weights: Dict[str, float] = {}
        for skill_id in skill_ids:
            skill_data = self.skills.get(skill_id, {})
            skill_tools = skill_data.get("tools", [])
            if not skill_tools:
                skill_weights[skill_id] = 1.0
                continue
            # Get coverage weights for this skill's tools (low coverage → high weight)
            tool_weights = self.coverage_tracker.get_coverage_weights(
                skill_tools, invert=True
            )
            if tool_weights:
                # Average inverted coverage weight across all skill tools
                skill_weights[skill_id] = sum(tool_weights.values()) / len(tool_weights)
            else:
                # No coverage data yet — give high weight (unexplored)
                skill_weights[skill_id] = 1.0

        # Floor weights so every eligible skill has a chance
        min_weight = max(0.01, min(skill_weights.values()) if skill_weights else 0.01)
        for skill_id in skill_weights:
            skill_weights[skill_id] = max(min_weight, skill_weights[skill_id])

        # Weighted sampling without replacement
        selected: List[str] = []
        remaining = dict(skill_weights)

        for _ in range(n):
            if not remaining:
                break
            total_w = sum(remaining.values())
            r = random.uniform(0, total_w)
            cumulative = 0.0
            chosen = list(remaining.keys())[-1]
            for sid, w in remaining.items():
                cumulative += w
                if r <= cumulative:
                    chosen = sid
                    break
            selected.append(chosen)
            del remaining[chosen]

        logger.debug(
            f"Coverage-weighted skill sample: {selected} "
            f"(weights: {{{', '.join(f'{k}: {v:.3f}' for k, v in skill_weights.items())}}})"
        )
        return selected

    def _resolve_skill_md_path(self, skill_id: str) -> Path:
        """Resolve the SKILL.md path for a skill, checking category subdirectory first."""
        skill_data = self.skills.get(skill_id, {})

        # If skill has a _skills_dir (from category loading), use it
        if "_skills_dir" in skill_data:
            return Path(skill_data["_skills_dir"]) / skill_id / "SKILL.md"

        # If skill has a _category, look in category subdirectory
        if "_category" in skill_data:
            return self.skills_dir / skill_data["_category"] / skill_id / "SKILL.md"

        # Default: look directly in skills_dir
        return self.skills_dir / skill_id / "SKILL.md"

    def load_skill_workflows(self, skill_ids: List[str]) -> str:
        """Load and concatenate SKILL.md files for given skill IDs.

        Note: This is the legacy method that loads all skills at once.
        For sequential exposure, use load_single_skill_workflow() instead.

        Args:
            skill_ids: List of skill IDs to load

        Returns:
            Concatenated workflow text with proper formatting
        """
        from prompts.skill_guided import (
            SKILL_WORKFLOW_TEMPLATE,
            SKILL_WORKFLOW_SEPARATOR,
        )

        workflows = []

        for skill_id in skill_ids:
            skill_md_path = self._resolve_skill_md_path(skill_id)

            if not skill_md_path.exists():
                logger.warning(f"SKILL.md not found for {skill_id}: {skill_md_path}")
                continue

            with open(skill_md_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            # Format using template
            formatted = SKILL_WORKFLOW_TEMPLATE.format(
                skill_id=skill_id, skill_content=content
            )
            workflows.append(formatted)

        if not workflows:
            raise ValueError(f"No SKILL.md files found for skills: {skill_ids}")

        # Use a generic header for multi-skill mode (no specific skill_id)
        generic_header = """
## Professional Workflow Guidance

You are given professional skill workflows below. Follow the steps in order to accomplish coherent, high-quality tasks.

**Important:**
- Read each workflow carefully and execute the steps in sequence
- Each step builds on the results of the previous one
- Use the exact tool call format shown in the examples (tool arguments must be JSON objects)

"""
        # Concatenate with header and separator
        concatenated = (
            generic_header + SKILL_WORKFLOW_SEPARATOR.join(workflows) + "\n"
        )

        logger.info(
            f"Loaded {len(workflows)} skill workflows ({len(concatenated)} chars)"
        )
        return concatenated

    def load_single_skill_workflow(self, skill_id: str, is_first: bool = True) -> str:
        """Load SKILL.md for a single skill (used in sequential exposure).

        Args:
            skill_id: Skill ID to load
            is_first: If True, include header (for system prompt);
                      if False, omit header (for mid-conversation injection)

        Returns:
            Formatted workflow text for a single skill
        """
        from prompts.skill_guided import (
            SKILL_WORKFLOW_HEADER,
            SKILL_WORKFLOW_TEMPLATE,
            SKILL_TRANSITION_TEMPLATE,
        )

        skill_md_path = self._resolve_skill_md_path(skill_id)

        if not skill_md_path.exists():
            raise FileNotFoundError(f"SKILL.md not found: {skill_md_path}")

        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        # Format using template
        formatted = SKILL_WORKFLOW_TEMPLATE.format(
            skill_id=skill_id, skill_content=content
        )

        if is_first:
            # First skill: include header with completion marker instruction
            header = SKILL_WORKFLOW_HEADER.format(skill_id=skill_id)
            return header + formatted + "\n"
        else:
            # Subsequent skills: use transition template
            return SKILL_TRANSITION_TEMPLATE.format(
                skill_id=skill_id, skill_content=formatted
            )

    def get_skill_step_tools(self, skill_id: str) -> List[str]:
        """Extract ordered step tools from a skill's SKILL.md.

        Returns the list of tools expected by each workflow step, in order.
        Used by SkillCompletionDetector for soft step-adherence scoring.

        Args:
            skill_id: Skill ID to extract step tools for

        Returns:
            Ordered list of tool names per step, empty if no steps found
        """
        _, step_tools = self._read_skill_md(skill_id)
        return step_tools

    def get_skill_content(self, skill_id: str) -> str:
        """Return the raw SKILL.md content for a skill.

        Used by SkillGuidanceInjector for force re-injection when the model
        has drifted off-track for too many consecutive steps.

        Args:
            skill_id: Skill ID to load content for

        Returns:
            Raw SKILL.md text, or empty string if not found.
        """
        content, _ = self._read_skill_md(skill_id)
        return content

    def _read_skill_md(self, skill_id: str) -> tuple:
        """Read a skill's SKILL.md and return (raw_content, step_tools).

        Cached internally on first read to avoid re-reading files during
        guidance injection and completion detection for the same skill.

        Args:
            skill_id: Skill ID to read

        Returns:
            (raw_content: str, step_tools: List[str])
        """
        from data_collection.sampling.skill_completion_detector import (
            SkillCompletionDetector,
        )

        skill_md_path = self._resolve_skill_md_path(skill_id)
        if not skill_md_path.exists():
            logger.warning(
                f"Cannot read SKILL.md: not found for {skill_id} at {skill_md_path}"
            )
            return "", []

        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        step_tools = SkillCompletionDetector.extract_step_tools(content)
        return content, step_tools

    def compute_exposed_tools(
        self, skill_selections: List[SkillSelection]
    ) -> List[Dict[str, Any]]:
        """Compute union of tools from selected skills.

        Args:
            skill_selections: List of selected skills

        Returns:
            List of tool dicts from all_tools
        """
        # Union of all tool names
        tool_names: Set[str] = set()
        for selection in skill_selections:
            tool_names.update(selection.tools)

        # Map to tool dicts
        exposed_tools = []
        for tool_name in tool_names:
            if tool_name in self._tool_map:
                exposed_tools.append(self._tool_map[tool_name])
            else:
                logger.warning(
                    f"Tool '{tool_name}' required by skills but not found in all_tools"
                )

        logger.info(
            f"Computed {len(exposed_tools)} exposed tools from {len(skill_selections)} skills"
        )
        return exposed_tools

    def compute_target_n(self, skill_selections: List[SkillSelection]) -> int:
        """Compute target number of tool calls from skill ranges.

        Uses the midpoint of each skill's tool_calls_range and sums them.

        Args:
            skill_selections: List of selected skills

        Returns:
            Target number of tool calls
        """
        total = 0
        for selection in skill_selections:
            min_calls, max_calls = selection.tool_calls_range
            midpoint = (min_calls + max_calls) // 2
            total += midpoint

        logger.info(
            f"Computed target_n={total} from {len(skill_selections)} skill ranges"
        )
        return total
