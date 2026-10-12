"""Experience extraction from successful trajectories (PRD 4.7).

Uses LLM to summarize successful trajectories into reusable experiences.
"""

import json
import logging
import uuid
import re
from typing import Dict, Any, Optional, List

from .experience_store import Experience
from prompts.experience import (
    EXPERIENCE_EXTRACTION_SYSTEM_PROMPT,
    EXPERIENCE_EXTRACTION_USER_TEMPLATE,
)

logger = logging.getLogger(__name__)


class ExperienceExtractor:
    """Extracts reusable experiences from successful trajectories using LLM summarization."""

    def __init__(self, maas_client, model_config, max_sample_calls: int = 5):
        """Initialize experience extractor.

        Args:
            maas_client: MaaS client for LLM calls
            model_config: Model configuration for experience extraction
            max_sample_calls: Maximum tool calls to include in prompt
        """
        self.maas_client = maas_client
        self.model_config = model_config
        self.max_sample_calls = max_sample_calls

    async def extract_experience(
        self, trajectory: Dict[str, Any], problem: Dict[str, Any]
    ) -> Optional[Experience]:
        """Extract a reusable experience from a successful trajectory.

        Args:
            trajectory: The trajectory dict (or StrictTrajectory-like object)
            problem: The synthesized problem dict

        Returns:
            Extracted Experience object, or None if extraction fails
        """
        try:
            # Extract tool calls from trajectory
            tool_calls = self._get_tool_calls(trajectory)
            if not tool_calls:
                logger.debug("No tool calls to extract experience from")
                return None

            # Build tool sequence
            tool_sequence = [
                tc.get("tool_name", tc.get("tool", "")) for tc in tool_calls
            ]
            successful_count = sum(1 for tc in tool_calls if tc.get("success", True))

            # Build sample calls for prompt
            sample_calls = self._build_sample_calls(tool_calls)

            # Build extraction prompt
            user_prompt = EXPERIENCE_EXTRACTION_USER_TEMPLATE.format(
                problem=problem.get("problem", ""),
                task_context=self._build_task_context(problem),
                tool_sequence=" -> ".join(tool_sequence[:10]),
                tool_count=len(tool_calls),
                successful_count=successful_count,
                sample_calls=sample_calls,
            )

            messages = [
                {"role": "system", "content": EXPERIENCE_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            # Call LLM for extraction
            response = await self.maas_client.generate_completion(
                messages=messages, model_config=self.model_config, tools=None
            )

            content = response.get("content", "{}")
            exp_data = self._parse_json_response(content)

            if not exp_data:
                logger.warning("Failed to parse experience extraction response")
                return None

            # Create Experience object
            experience = Experience(
                experience_id=str(uuid.uuid4())[:8],
                description=exp_data.get("experience_description",
                                        exp_data.get("skill_description", "")),
                tool_sequence=tool_sequence,
                context_summary=exp_data.get("context_summary", ""),
                action_sequence=exp_data.get("action_sequence", None),
                confidence=exp_data.get("confidence", 1.0),
                metadata=problem.get("experience_metadata", {}),
            )

            logger.info(f"Extracted experience: {experience.description[:100]}")
            return experience

        except Exception as e:
            logger.warning(f"Experience extraction failed: {e}")
            return None

    def _get_tool_calls(self, trajectory: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool calls from trajectory (supports multiple formats)."""
        # Try direct tool_calls attribute
        if hasattr(trajectory, "tool_calls"):
            return [
                {
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments,
                    "success": tc.success,
                    "result": tc.result[:500] if tc.result else "",
                }
                for tc in trajectory.tool_calls
            ]

        # Try dict format
        if isinstance(trajectory, dict):
            if "tool_calls" in trajectory:
                return trajectory["tool_calls"]

            # Extract from messages
            calls = []
            messages = trajectory.get("messages", [])
            for msg in messages:
                if msg.get("role") == "assistant":
                    for tc in msg.get("tool_calls", []):
                        calls.append(
                            {
                                "tool_name": tc.get("function", {}).get("name", ""),
                                "arguments": tc.get("function", {}).get(
                                    "arguments", {}
                                ),
                                "success": True,
                            }
                        )
            return calls

        return []

    def _build_task_context(self, problem: Dict[str, Any]) -> str:
        """Build compact visible context for experience extraction."""
        context = problem.get("experience_context")
        if isinstance(context, str) and context.strip():
            return context.strip()
        if isinstance(context, dict):
            return json.dumps(context, ensure_ascii=False, indent=2)[:3000]

        fields = []
        for key in (
            "task_type",
            "world_id",
            "world_domain",
            "stage",
            "tier",
            "phase",
            "visible_tools",
            "anchor_usage",
            "state_evidence",
        ):
            value = problem.get(key)
            if value not in (None, "", [], {}):
                fields.append(f"- {key}: {value}")
        return "\n".join(fields) if fields else "No additional visible context."

    def _build_sample_calls(self, tool_calls: List[Dict[str, Any]]) -> str:
        """Build sample calls string for prompt."""
        samples = []
        for i, tc in enumerate(tool_calls[: self.max_sample_calls]):
            tool_name = tc.get("tool_name", tc.get("tool", "unknown"))
            args = tc.get("arguments", {})
            result = str(tc.get("result", "") or "")
            result = self._redact_long_result(result)
            # Anonymize paths
            args_str = json.dumps(args, ensure_ascii=False)[:200]
            result_suffix = f" -> {result}" if result else ""
            samples.append(f"{i + 1}. {tool_name}({args_str}){result_suffix}")

        if len(tool_calls) > self.max_sample_calls:
            samples.append(
                f"... and {len(tool_calls) - self.max_sample_calls} more calls"
            )

        return "\n".join(samples)

    def _redact_long_result(self, result: str) -> str:
        """Keep evidence useful while preventing memorization of huge outputs."""
        if not result:
            return ""
        compact = " ".join(result.split())
        compact = re.sub(r"https://github\.com/[^\\s\"']+", "<github_url>", compact)
        compact = re.sub(r"mcpmark-eval-[A-Za-z0-9_-]+", "<eval_org>", compact)
        return compact[:500]

    def _parse_json_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response (supports <experience> and legacy <skill> tags)."""
        if not content:
            return None

        # Try finding <experience> tags first
        exp_match = re.search(r"<experience>(.*?)</experience>", content, re.DOTALL)
        if exp_match:
            try:
                return json.loads(exp_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Fallback: Try legacy <skill> tags
        skill_match = re.search(r"<skill>(.*?)</skill>", content, re.DOTALL)
        if skill_match:
            try:
                return json.loads(skill_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Fallback: Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Fallback: Try to find JSON block in response
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None
