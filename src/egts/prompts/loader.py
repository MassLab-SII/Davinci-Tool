"""Unified prompt loader for executable-world synthesis and exploration."""

from __future__ import annotations

from typing import Any, Dict

from prompts import exploration
from prompts import synthesis
from prompts import self_questioning
from prompts import synthesis_judge


class _SafeFormatDict(dict):
    """Return a readable placeholder when a key is missing."""

    def __missing__(self, key: str) -> str:
        return f"<missing:{key}>"


class PromptLoader:
    """Load one shared prompt set for all executable worlds.

    The loader retains the `mcp_server` argument for API compatibility. Every
    world routes to the shared modules in `prompts/`; world-specific context
    should be passed as data fields rather than implemented as new prompt files.
    """

    def __init__(self, mcp_server: str = "filesystem"):
        self.mcp_server = (mcp_server or "filesystem").lower()

    def _get_synth_module(self):
        return synthesis

    def _get_sq_module(self):
        return self_questioning

    def _get_judge_module(self):
        return synthesis_judge

    @staticmethod
    def _pick_language(language: str, zh_value: str, en_value: str) -> str:
        return zh_value if (language or "en").lower() == "zh" else en_value

    @staticmethod
    def _safe_format(template: str, **kwargs: Any) -> str:
        if not template:
            return ""
        values = _SafeFormatDict()
        values.update(kwargs)
        return template.format_map(values)

    def get_mutation_rewrite_system(self, language: str = "en") -> str:
        synth = self._get_synth_module()
        zh = getattr(synth, "PROBLEM_REWRITE_SYSTEM_PROMPT_ZH")
        en = getattr(synth, "PROBLEM_REWRITE_SYSTEM_PROMPT_EN")
        return self._pick_language(language, zh, en)

    def get_mutation_rewrite_user(self, language: str = "en", **kwargs: Any) -> str:
        synth = self._get_synth_module()
        zh = getattr(synth, "PROBLEM_REWRITE_USER_TEMPLATE_ZH")
        en = getattr(synth, "PROBLEM_REWRITE_USER_TEMPLATE_EN")
        template = self._pick_language(language, zh, en)
        return self._safe_format(template, **kwargs)

    def get_retrieval_rewrite_system(self, language: str = "en") -> str:
        synth = self._get_synth_module()
        zh = getattr(synth, "RETRIEVAL_REWRITE_SYSTEM_PROMPT_ZH")
        en = getattr(synth, "RETRIEVAL_REWRITE_SYSTEM_PROMPT_EN")
        return self._pick_language(language, zh, en)

    def get_retrieval_rewrite_user(self, language: str = "en", **kwargs: Any) -> str:
        synth = self._get_synth_module()
        zh = getattr(synth, "RETRIEVAL_REWRITE_USER_TEMPLATE_ZH")
        en = getattr(synth, "RETRIEVAL_REWRITE_USER_TEMPLATE_EN")
        template = self._pick_language(language, zh, en)
        return self._safe_format(template, **kwargs)

    def get_self_questioning_system(self, language: str = "en") -> str:
        sq = self._get_sq_module()
        zh = getattr(sq, "CANDIDATE_GENERATION_SYSTEM_PROMPT_ZH")
        en = getattr(sq, "CANDIDATE_GENERATION_SYSTEM_PROMPT_EN")
        return self._pick_language(language, zh, en)

    def get_self_questioning_user(self, language: str = "en", **kwargs: Any) -> str:
        sq = self._get_sq_module()
        zh = getattr(sq, "CANDIDATE_GENERATION_USER_TEMPLATE_ZH")
        en = getattr(sq, "CANDIDATE_GENERATION_USER_TEMPLATE_EN")
        template = self._pick_language(language, zh, en)
        return self._safe_format(template, **kwargs)

    def get_exploration_prompt(self, **kwargs: Any) -> str:
        """Return the unified executable-world exploration prompt."""
        values = dict(kwargs)
        values.setdefault("world_context", "No additional world context provided.")
        values.setdefault("tool_names", "")
        return self._safe_format(exploration.EXPLORATION_USER_PROMPT, **values)

    def get_exploration_prompt_with_objective(self, **kwargs: Any) -> str:
        """Return the task-objective-driven exploration prompt.

        Asks the model to conceive a concrete task from world context first,
        then explore to accomplish it. Produces goal-directed trajectories.
        """
        values = dict(kwargs)
        values.setdefault("world_context", "No additional world context provided.")
        values.setdefault("tool_names", "")
        return self._safe_format(exploration.EXPLORATION_USER_PROMPT_WITH_OBJECTIVE, **values)

    def get_judge_prompt_bundle(self) -> Dict[str, str]:
        module = self._get_judge_module()
        keys = [
            "JUDGE_PROBLEM_SYSTEM_PROMPT",
            "JUDGE_PROBLEM_USER_TEMPLATE",
            "REFINE_PROBLEM_SYSTEM_PROMPT",
            "REFINE_PROBLEM_USER_TEMPLATE",
            "JUDGE_TRAJECTORY_SYSTEM_PROMPT",
            "JUDGE_TRAJECTORY_USER_TEMPLATE",
            "REWRITE_TRAJECTORY_SYSTEM_PROMPT",
            "REWRITE_TRAJECTORY_USER_TEMPLATE",
            "JUDGE_TRAJECTORY_HARD_SYSTEM_PROMPT",
            "JUDGE_TRAJECTORY_HARD_USER_TEMPLATE",
            "JUDGE_TRAJECTORY_SOFT_SYSTEM_PROMPT",
            "JUDGE_TRAJECTORY_SOFT_USER_TEMPLATE",
            "POLISH_FALLBACK_TRAJECTORY_SYSTEM_PROMPT",
            "POLISH_FALLBACK_TRAJECTORY_USER_TEMPLATE",
            "JUDGE_CANDIDATE_SYSTEM_PROMPT",
            "JUDGE_CANDIDATE_USER_TEMPLATE",
        ]
        bundle = {}
        for key in keys:
            value = getattr(module, key, None)
            if value is None:
                value = getattr(synthesis_judge, key, "")
            bundle[key] = value
        return bundle
