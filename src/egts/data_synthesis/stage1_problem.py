"""Stage-1 problem consistency loop for data_synthesis pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from data_collection.problem_synthesizer import TaskType

logger = logging.getLogger(__name__)


@dataclass
class Stage1ProblemResult:
    consistent: bool
    final_problem: str
    attempts: int
    accept_mode: str
    last_failure_reason: str


class Stage1ProblemMixin:
    """Mixin that encapsulates stage-1 problem synthesis/judging loop."""

    async def _run_stage1_problem_consistency(
        self,
        *,
        episode_dir: str,
        problem_text: str,
        task_type: str,
        action_summary: str,
        expected_tool_steps: int,
        ordered_tool_calls: List[Dict[str, Any]],
        prompt_bundle: Dict[str, str],
        collection_task_type: str | None = None,
    ) -> Stage1ProblemResult:
        final_problem = problem_text
        consistent = False
        problem_attempts = 0
        problem_accept_mode = "unaccepted"
        problem_last_failure_reason = "N/A"

        for attempt in range(self.max_problem_refine_loops):
            problem_attempts = attempt + 1
            self._set_call_context(
                stage="stage1_problem_judge",
                attempt=problem_attempts,
                task_type=task_type,
            )
            try:
                is_valid, reason = await self._judge_problem(
                    final_problem, action_summary, prompt_bundle, task_type=task_type
                )
            finally:
                self._clear_call_context()
            if is_valid:
                heuristic_ok, heuristic_reason = self._heuristic_problem_check(
                    final_problem, expected_tool_steps, task_type,
                    collection_task_type=collection_task_type,
                )
                if heuristic_ok:
                    consistent = True
                    problem_accept_mode = "judge_pass"
                    break
                logger.info(
                    "Stage 1 judge passed but heuristic rejected: %s", heuristic_reason
                )
                reason = f"Heuristic reject: {heuristic_reason}"

            logger.info("Stage 1 Fail (Attempt %d): %s", attempt + 1, reason)
            problem_last_failure_reason = reason
            if self._is_problem_refine_low_yield(reason, task_type):
                logger.info(
                    "Stage 1 early-stop after attempt %d due to low-yield failure: %s",
                    attempt + 1,
                    reason,
                )
                break
            try:
                self._set_call_context(
                    stage="stage1_problem_refine",
                    attempt=problem_attempts,
                    task_type=task_type,
                )
                refined = await self._refine_problem(
                    final_problem, action_summary, reason, prompt_bundle
                )
            except Exception as e:
                logger.warning("Stage 1 refine failed on attempt %d: %s", attempt + 1, e)
                break
            finally:
                self._clear_call_context()
            refined = (refined or "").strip()
            if not refined:
                logger.warning("Stage 1 produced empty refinement; stopping.")
                break
            final_problem = refined

        if (not consistent) and str(task_type).lower() == TaskType.MUTATION.value:
            grounded_problem = self._build_grounded_mutation_problem(ordered_tool_calls)
            if grounded_problem and grounded_problem.strip() != final_problem.strip():
                logger.info(
                    "Stage 1 attempting grounded mutation-problem repair for %s",
                    episode_dir,
                )
                problem_attempts += 1
                self._set_call_context(
                    stage="stage1_problem_grounded_repair",
                    attempt=problem_attempts,
                    task_type=task_type,
                )
                try:
                    repair_ok, repair_reason = await self._judge_problem(
                        grounded_problem, action_summary, prompt_bundle, task_type=task_type
                    )
                finally:
                    self._clear_call_context()

                if repair_ok:
                    heuristic_ok, heuristic_reason = self._heuristic_problem_check(
                        grounded_problem, expected_tool_steps, task_type,
                        collection_task_type=collection_task_type,
                    )
                    if heuristic_ok:
                        final_problem = grounded_problem
                        consistent = True
                        problem_accept_mode = "judge_pass"
                        problem_last_failure_reason = "N/A"
                        logger.info("Stage 1 grounded mutation-problem repair accepted.")
                    else:
                        problem_last_failure_reason = (
                            f"Heuristic reject after grounded repair: {heuristic_reason}"
                        )
                        logger.info(
                            "Stage 1 grounded repair rejected by heuristic: %s",
                            heuristic_reason,
                        )
                else:
                    if repair_reason:
                        problem_last_failure_reason = repair_reason
                    logger.info(
                        "Stage 1 grounded repair rejected by judge: %s", repair_reason
                    )

        if (not consistent) and self.enable_heuristic_fallback:
            heuristic_ok, heuristic_reason = self._heuristic_problem_check(
                final_problem, expected_tool_steps, task_type,
                collection_task_type=collection_task_type,
            )
            if heuristic_ok:
                consistent = True
                problem_accept_mode = "heuristic_fallback_pass"
                logger.info(
                    "Stage 1 accepted by heuristic fallback: %s", heuristic_reason
                )
            else:
                problem_last_failure_reason = heuristic_reason

        return Stage1ProblemResult(
            consistent=consistent,
            final_problem=final_problem,
            attempts=problem_attempts,
            accept_mode=problem_accept_mode,
            last_failure_reason=problem_last_failure_reason,
        )

