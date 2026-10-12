"""Stage-2 trajectory rewrite/judge loop for data_synthesis pipeline."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class Stage2TrajectoryResult:
    realistic: bool
    final_messages: List[Dict[str, Any]]
    attempts: int
    accept_mode: str
    last_failure_reason: str
    # Phase 1: Quality tier metadata
    quality_tier: str = ""  # "high_quality" | "acceptable" | "fallback_based"
    hard_judge_pass: bool = False
    soft_judge_pass: bool = False
    soft_judge_score: float = 0.0
    soft_judge_issues: List[str] = None

    def __post_init__(self):
        if self.soft_judge_issues is None:
            self.soft_judge_issues = []


class Stage2TrajectoryMixin:
    """Mixin that encapsulates stage-2 trajectory rewrite+judge loop."""

    async def _run_stage2_trajectory_rewrite(
        self,
        *,
        final_problem: str,
        task_type: str,
        current_messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        reference_answer: str,
        prompt_bundle: Dict[str, str],
    ) -> Stage2TrajectoryResult:
        """Route to appropriate trajectory rewrite strategy based on config.

        Routing logic:
        1. Check trajectory_mode config:
           - "llm_rewrite": Full LLM rewrite with dual-judge or single-judge
           - "fallback_polish": Fallback skeleton + LLM polish + dual-judge
           - "fallback_only": Pure rule-based fallback (no LLM polish)
        2. For llm_rewrite mode, check use_dual_judge:
           - True: dual-judge validation (hard + soft)
           - False: legacy single-judge validation
        """
        # Check trajectory mode
        trajectory_mode = getattr(self, "trajectory_mode", "llm_rewrite")

        # Mode: fallback_polish
        if trajectory_mode == "fallback_polish":
            return await self._run_stage2_fallback_polish(
                original_messages=current_messages,
                ordered_tool_calls=ordered_tool_calls,
                final_problem=final_problem,
                reference_answer=reference_answer,
                task_type=task_type,
                expected_tool_steps=len(ordered_tool_calls),
                prompt_bundle=prompt_bundle,
            )

        # Mode: fallback_only
        if trajectory_mode == "fallback_only":
            # Generate fallback skeleton without polish
            fallback_messages = self._build_structured_fallback_messages(
                messages=current_messages,
                ordered_tool_calls=ordered_tool_calls,
                problem=final_problem,
                reference_answer=reference_answer,
                task_type=task_type,
            )

            if not fallback_messages:
                return Stage2TrajectoryResult(
                    realistic=False,
                    final_messages=current_messages,
                    attempts=0,
                    accept_mode="fallback_skeleton_failed",
                    last_failure_reason="Failed to generate fallback skeleton",
                    quality_tier="",
                    hard_judge_pass=False,
                    soft_judge_pass=False,
                    soft_judge_score=0.0,
                    soft_judge_issues=[],
                )

            # Validate with dual-judge if enabled
            use_dual_judge = getattr(self, "use_dual_judge", True)
            expected_tool_steps = len(ordered_tool_calls)

            if use_dual_judge:
                fallback_text = self._messages_to_text(fallback_messages)

                # Hard + Soft judge in parallel
                (hard_ok, hard_reason), (soft_ok, soft_reason, soft_issues) = (
                    await asyncio.gather(
                        self._judge_trajectory_hard(
                            final_problem,
                            fallback_text,
                            expected_tool_steps,
                            prompt_bundle,
                            task_type,
                            reference_answer,
                        ),
                        self._judge_trajectory_soft(
                            final_problem,
                            fallback_text,
                            expected_tool_steps,
                            prompt_bundle,
                            task_type,
                        ),
                    )
                )

                # Heuristic check
                heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                    fallback_messages,
                    expected_tool_steps,
                    task_type=task_type,
                    reference_answer=reference_answer,
                    problem=final_problem,
                    ordered_tool_calls=ordered_tool_calls,
                )

                if hard_ok and heuristic_ok:
                    return Stage2TrajectoryResult(
                        realistic=True,
                        final_messages=fallback_messages,
                        attempts=1,
                        accept_mode="fallback_only_dual_judge_pass",
                        last_failure_reason="",
                        quality_tier="fallback_based",
                        hard_judge_pass=True,
                        soft_judge_pass=soft_ok,
                        soft_judge_score=0.0,
                        soft_judge_issues=soft_issues,
                    )
                else:
                    return Stage2TrajectoryResult(
                        realistic=False,
                        final_messages=fallback_messages,
                        attempts=1,
                        accept_mode="fallback_only_rejected",
                        last_failure_reason=hard_reason if not hard_ok else heuristic_reason,
                        quality_tier="",
                        hard_judge_pass=hard_ok,
                        soft_judge_pass=soft_ok,
                        soft_judge_score=0.0,
                        soft_judge_issues=soft_issues,
                    )
            else:
                # Legacy single-judge for fallback_only
                heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                    fallback_messages,
                    expected_tool_steps,
                    task_type=task_type,
                    reference_answer=reference_answer,
                    problem=final_problem,
                    ordered_tool_calls=ordered_tool_calls,
                )

                return Stage2TrajectoryResult(
                    realistic=heuristic_ok,
                    final_messages=fallback_messages,
                    attempts=1,
                    accept_mode="fallback_only_heuristic" if heuristic_ok else "fallback_only_rejected",
                    last_failure_reason="" if heuristic_ok else heuristic_reason,
                    quality_tier="fallback_based" if heuristic_ok else "",
                    hard_judge_pass=False,
                    soft_judge_pass=False,
                    soft_judge_score=0.0,
                    soft_judge_issues=[],
                )

        # Mode: llm_rewrite (default)
        use_dual_judge = getattr(self, "use_dual_judge", True)

        if use_dual_judge:
            return await self._run_stage2_trajectory_rewrite_dual_judge(
                final_problem=final_problem,
                task_type=task_type,
                current_messages=current_messages,
                ordered_tool_calls=ordered_tool_calls,
                reference_answer=reference_answer,
                prompt_bundle=prompt_bundle,
            )
        else:
            # Legacy single-judge mode
            return await self._run_stage2_trajectory_rewrite_single_judge(
                final_problem=final_problem,
                task_type=task_type,
                current_messages=current_messages,
                ordered_tool_calls=ordered_tool_calls,
                reference_answer=reference_answer,
                prompt_bundle=prompt_bundle,
            )


    async def _run_stage2_trajectory_rewrite_single_judge(
        self,
        *,
        final_problem: str,
        task_type: str,
        current_messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        reference_answer: str,
        prompt_bundle: Dict[str, str],
    ) -> Stage2TrajectoryResult:
        """Legacy single-judge trajectory rewrite (backward compatible)."""
        expected_tool_steps = len(ordered_tool_calls)
        final_messages = current_messages
        realistic = False
        trajectory_attempts = 0
        critique = "N/A"
        trajectory_accept_mode = "unaccepted"
        trajectory_last_failure_reason = "N/A"

        for attempt in range(self.max_trajectory_refine_loops):
            trajectory_attempts = attempt + 1
            self._set_call_context(
                stage="stage2_trajectory_rewrite",
                attempt=trajectory_attempts,
                task_type=task_type,
            )
            try:
                rewritten = await self._rewrite_trajectory_with_structure(
                    problem=final_problem,
                    messages=current_messages,
                    ordered_tool_calls=ordered_tool_calls,
                    reference_answer=reference_answer,
                    task_type=task_type,
                    critique=critique,
                    prompt_bundle=prompt_bundle,
                )
            finally:
                self._clear_call_context()
            candidate_messages = rewritten or final_messages
            candidate_messages = self._normalize_messages_for_output(
                messages=candidate_messages,
                problem=final_problem,
                ordered_tool_calls=ordered_tool_calls,
                task_type=task_type,
                reference_answer=reference_answer,
            )

            full_text = self._messages_to_text(candidate_messages)
            self._set_call_context(
                stage="stage2_trajectory_judge",
                attempt=trajectory_attempts,
                task_type=task_type,
            )
            try:
                is_valid, reason = await self._judge_trajectory(
                    final_problem,
                    full_text,
                    expected_tool_steps,
                    prompt_bundle,
                    task_type=task_type,
                    reference_answer=reference_answer,
                )
            finally:
                self._clear_call_context()
            if is_valid:
                heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                    candidate_messages,
                    expected_tool_steps,
                    task_type=task_type,
                    reference_answer=reference_answer,
                    problem=final_problem,
                    ordered_tool_calls=ordered_tool_calls,
                )
                if not heuristic_ok:
                    is_valid = False
                    reason = f"Heuristic reject: {heuristic_reason}"
            if is_valid:
                realistic = True
                final_messages = candidate_messages
                trajectory_accept_mode = "primary_judge_pass"
                break

            logger.info("Stage 2 Fail (Attempt %d): %s", attempt + 1, reason)
            critique = reason
            trajectory_last_failure_reason = reason
            final_messages = candidate_messages
            if self._is_trajectory_refine_low_yield(reason):
                logger.info(
                    "Stage 2 early-stop after attempt %d due to low-yield failure: %s",
                    attempt + 1,
                    reason,
                )
                break

        if (not realistic) and self.enable_heuristic_fallback:
            fallback_messages = self._build_structured_fallback_messages(
                messages=current_messages,
                ordered_tool_calls=ordered_tool_calls,
                problem=final_problem,
                reference_answer=reference_answer,
                task_type=task_type,
            )
            if fallback_messages:
                fallback_messages = self._normalize_messages_for_output(
                    messages=fallback_messages,
                    problem=final_problem,
                    ordered_tool_calls=ordered_tool_calls,
                    task_type=task_type,
                    reference_answer=reference_answer,
                )
                full_text = self._messages_to_text(fallback_messages)
                self._set_call_context(
                    stage="stage2_fallback_judge",
                    attempt=trajectory_attempts,
                    task_type=task_type,
                )
                try:
                    judge_ok, judge_reason = await self._judge_trajectory(
                        final_problem,
                        full_text,
                        expected_tool_steps,
                        prompt_bundle,
                        task_type=task_type,
                        reference_answer=reference_answer,
                    )
                finally:
                    self._clear_call_context()
                if judge_ok:
                    heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                        fallback_messages,
                        expected_tool_steps,
                        task_type=task_type,
                        reference_answer=reference_answer,
                        problem=final_problem,
                        ordered_tool_calls=ordered_tool_calls,
                    )
                    if heuristic_ok:
                        realistic = True
                        final_messages = fallback_messages
                        trajectory_accept_mode = "structured_fallback_judge_pass"
                        logger.info(
                            "Stage 2 accepted via structured fallback + judge: %s",
                            judge_reason,
                        )
                    else:
                        logger.info(
                            "Stage 2 fallback judge passed but heuristic rejected: %s",
                            heuristic_reason,
                        )
                if not realistic:
                    heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                        fallback_messages,
                        expected_tool_steps,
                        task_type=task_type,
                        reference_answer=reference_answer,
                        problem=final_problem,
                        ordered_tool_calls=ordered_tool_calls,
                    )
                    if heuristic_ok:
                        realistic = True
                        final_messages = fallback_messages
                        trajectory_accept_mode = "structured_fallback_heuristic_pass"
                        logger.info(
                            "Stage 2 accepted by heuristic fallback: %s",
                            heuristic_reason,
                        )
                    else:
                        trajectory_last_failure_reason = heuristic_reason

        return Stage2TrajectoryResult(
            realistic=realistic,
            final_messages=final_messages,
            attempts=trajectory_attempts,
            accept_mode=trajectory_accept_mode,
            last_failure_reason=trajectory_last_failure_reason,
        )

    async def _judge_trajectory_hard(
        self,
        problem: str,
        trajectory_full: str,
        expected_tool_steps: int,
        prompt_bundle: Dict[str, str],
        task_type: str,
        reference_answer: str,
        use_relaxed: bool = False,
    ) -> tuple[bool, str]:
        """Judge trajectory for hard constraints (factual consistency only).

        Returns:
            (consistent, reason)
        """
        judge_system = prompt_bundle.get("JUDGE_TRAJECTORY_HARD_SYSTEM_PROMPT")
        judge_user_template = prompt_bundle.get("JUDGE_TRAJECTORY_HARD_USER_TEMPLATE")

        if not judge_system or not judge_user_template:
            logger.warning(
                "Hard judge prompts not found in bundle, falling back to single judge"
            )
            return await self._judge_trajectory(
                problem,
                trajectory_full,
                expected_tool_steps,
                prompt_bundle,
                task_type=task_type,
                reference_answer=reference_answer,
            )

        judge_user = judge_user_template.format(
            task_type=task_type,
            problem=problem,
            required_tool_steps=expected_tool_steps,
            require_final_answer=self.require_final_answer,
            reference_answer=reference_answer or "N/A",
            trajectory_full=trajectory_full,
        )

        result = await self._call_judge_model(
            system_prompt=judge_system,
            user_prompt=judge_user,
            use_relaxed=use_relaxed,
        )

        if not result:
            return False, "Hard judge call failed"

        consistent = result.get("consistent", False)
        reason = result.get("reason", "No reason provided")
        return consistent, reason

    async def _judge_trajectory_soft(
        self,
        problem: str,
        trajectory_full: str,
        expected_tool_steps: int,
        prompt_bundle: Dict[str, str],
        task_type: str,
        use_relaxed: bool = False,
    ) -> tuple[bool, str, List[str]]:
        """Judge trajectory for soft constraints (style quality only).

        Returns:
            (realistic, reason, issues)
        """
        judge_system = prompt_bundle.get("JUDGE_TRAJECTORY_SOFT_SYSTEM_PROMPT")
        judge_user_template = prompt_bundle.get("JUDGE_TRAJECTORY_SOFT_USER_TEMPLATE")

        if not judge_system or not judge_user_template:
            logger.warning(
                "Soft judge prompts not found in bundle, skipping soft judge"
            )
            return True, "Soft judge not available", []

        judge_user = judge_user_template.format(
            task_type=task_type,
            problem=problem,
            require_plan=self.require_planning_step,
            required_tool_steps=expected_tool_steps,
            trajectory_full=trajectory_full,
        )

        result = await self._call_judge_model(
            system_prompt=judge_system,
            user_prompt=judge_user,
            use_relaxed=use_relaxed,
        )

        if not result:
            return False, "Soft judge call failed", []

        realistic = result.get("realistic", False)
        reason = result.get("reason", "No reason provided")
        issues = result.get("issues", [])
        return realistic, reason, issues

    async def _run_stage2_trajectory_rewrite_dual_judge(
        self,
        *,
        final_problem: str,
        task_type: str,
        current_messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        reference_answer: str,
        prompt_bundle: Dict[str, str],
    ) -> Stage2TrajectoryResult:
        """Stage 2 trajectory rewrite with dual-judge validation.

        Hard judge (factual consistency) is one-vote veto.
        Soft judge (style quality) is advisory only.
        """
        expected_tool_steps = len(ordered_tool_calls)
        final_messages = current_messages
        realistic = False
        trajectory_attempts = 0
        critique = "N/A"
        trajectory_accept_mode = "unaccepted"
        trajectory_last_failure_reason = "N/A"

        # Quality tier tracking
        quality_tier = ""
        hard_judge_pass = False
        soft_judge_pass = False
        soft_judge_score = 0.0
        soft_judge_issues = []

        for attempt in range(self.max_trajectory_refine_loops):
            trajectory_attempts = attempt + 1
            self._set_call_context(
                stage="stage2_trajectory_rewrite",
                attempt=trajectory_attempts,
                task_type=task_type,
            )
            try:
                rewritten = await self._rewrite_trajectory_with_structure(
                    problem=final_problem,
                    messages=current_messages,
                    ordered_tool_calls=ordered_tool_calls,
                    reference_answer=reference_answer,
                    task_type=task_type,
                    critique=critique,
                    prompt_bundle=prompt_bundle,
                )
            finally:
                self._clear_call_context()

            candidate_messages = rewritten or final_messages
            candidate_messages = self._normalize_messages_for_output(
                messages=candidate_messages,
                problem=final_problem,
                ordered_tool_calls=ordered_tool_calls,
                task_type=task_type,
                reference_answer=reference_answer,
            )

            full_text = self._messages_to_text(candidate_messages)

            # Hard + Soft judge in parallel
            self._set_call_context(
                stage="stage2_trajectory_judge",
                attempt=trajectory_attempts,
                task_type=task_type,
            )
            try:
                (hard_consistent, hard_reason), (soft_realistic, soft_reason, soft_issues) = (
                    await asyncio.gather(
                        self._judge_trajectory_hard(
                            final_problem,
                            full_text,
                            expected_tool_steps,
                            prompt_bundle,
                            task_type=task_type,
                            reference_answer=reference_answer,
                        ),
                        self._judge_trajectory_soft(
                            final_problem,
                            full_text,
                            expected_tool_steps,
                            prompt_bundle,
                            task_type=task_type,
                        ),
                    )
                )
            finally:
                self._clear_call_context()

            if not hard_consistent:
                logger.info(
                    "Stage 2 Hard Judge Fail (Attempt %d): %s",
                    attempt + 1,
                    hard_reason,
                )
                critique = hard_reason
                trajectory_last_failure_reason = hard_reason
                final_messages = candidate_messages

                if self._is_trajectory_refine_low_yield(hard_reason):
                    logger.info(
                        "Stage 2 early-stop after attempt %d due to low-yield failure: %s",
                        attempt + 1,
                        hard_reason,
                    )
                    break
                continue

            # Heuristic check
            heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                candidate_messages,
                expected_tool_steps,
                task_type=task_type,
                reference_answer=reference_answer,
                problem=final_problem,
                ordered_tool_calls=ordered_tool_calls,
            )

            if not heuristic_ok:
                logger.info(
                    "Stage 2 Heuristic Fail (Attempt %d): %s",
                    attempt + 1,
                    heuristic_reason,
                )
                critique = f"Heuristic reject: {heuristic_reason}"
                trajectory_last_failure_reason = heuristic_reason
                final_messages = candidate_messages
                continue

            # Accept: hard judge + heuristic passed
            realistic = True
            final_messages = candidate_messages
            trajectory_accept_mode = "dual_judge_pass"
            hard_judge_pass = True
            soft_judge_pass = soft_realistic
            soft_judge_issues = soft_issues

            # Determine quality tier
            if soft_realistic:
                quality_tier = "high_quality"
                logger.info(
                    "Stage 2 accepted (high_quality): both hard and soft judges passed"
                )
            else:
                quality_tier = "acceptable"
                logger.info(
                    "Stage 2 accepted (acceptable): hard judge passed, soft judge failed: %s",
                    soft_reason,
                )
            break

        # Fallback handling (if enabled and not yet accepted)
        if (not realistic) and self.enable_heuristic_fallback:
            fallback_messages = self._build_structured_fallback_messages(
                messages=current_messages,
                ordered_tool_calls=ordered_tool_calls,
                problem=final_problem,
                reference_answer=reference_answer,
                task_type=task_type,
            )
            if fallback_messages:
                fallback_messages = self._normalize_messages_for_output(
                    messages=fallback_messages,
                    problem=final_problem,
                    ordered_tool_calls=ordered_tool_calls,
                    task_type=task_type,
                    reference_answer=reference_answer,
                )
                full_text = self._messages_to_text(fallback_messages)

                # Hard + Soft judge for fallback in parallel
                self._set_call_context(
                    stage="stage2_fallback_judge",
                    attempt=trajectory_attempts,
                    task_type=task_type,
                )
                try:
                    (hard_ok, hard_reason), (soft_ok, soft_reason, soft_issues) = (
                        await asyncio.gather(
                            self._judge_trajectory_hard(
                                final_problem,
                                full_text,
                                expected_tool_steps,
                                prompt_bundle,
                                task_type=task_type,
                                reference_answer=reference_answer,
                            ),
                            self._judge_trajectory_soft(
                                final_problem,
                                full_text,
                                expected_tool_steps,
                                prompt_bundle,
                                task_type=task_type,
                            ),
                        )
                    )
                finally:
                    self._clear_call_context()

                if hard_ok:

                    heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                        fallback_messages,
                        expected_tool_steps,
                        task_type=task_type,
                        reference_answer=reference_answer,
                        problem=final_problem,
                        ordered_tool_calls=ordered_tool_calls,
                    )

                    if heuristic_ok:
                        realistic = True
                        final_messages = fallback_messages
                        trajectory_accept_mode = "structured_fallback_dual_judge_pass"
                        hard_judge_pass = True
                        soft_judge_pass = soft_ok
                        soft_judge_issues = soft_issues
                        quality_tier = "fallback_based"
                        logger.info(
                            "Stage 2 accepted via structured fallback (fallback_based): hard=%s, soft=%s",
                            hard_ok,
                            soft_ok,
                        )

                if not realistic:
                    # Try heuristic-only fallback
                    heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                        fallback_messages,
                        expected_tool_steps,
                        task_type=task_type,
                        reference_answer=reference_answer,
                        problem=final_problem,
                        ordered_tool_calls=ordered_tool_calls,
                    )
                    if heuristic_ok:
                        realistic = True
                        final_messages = fallback_messages
                        trajectory_accept_mode = "structured_fallback_heuristic_pass"
                        quality_tier = "fallback_based"
                        logger.info(
                            "Stage 2 accepted by heuristic fallback (fallback_based): %s",
                            heuristic_reason,
                        )
                    else:
                        trajectory_last_failure_reason = heuristic_reason

        return Stage2TrajectoryResult(
            realistic=realistic,
            final_messages=final_messages,
            attempts=trajectory_attempts,
            accept_mode=trajectory_accept_mode,
            last_failure_reason=trajectory_last_failure_reason,
            quality_tier=quality_tier,
            hard_judge_pass=hard_judge_pass,
            soft_judge_pass=soft_judge_pass,
            soft_judge_score=soft_judge_score,
            soft_judge_issues=soft_judge_issues,
        )

    async def _run_stage2_fallback_polish(
        self,
        original_messages: List[Dict[str, Any]],
        ordered_tool_calls: List[Dict[str, Any]],
        final_problem: str,
        reference_answer: str,
        task_type: str,
        expected_tool_steps: int,
        prompt_bundle: Dict[str, str],
    ) -> Stage2TrajectoryResult:
        """Stage 2 trajectory generation using fallback+polish strategy.

        Pipeline:
        1. Generate rule-based fallback skeleton
        2. Polish skeleton with LLM (inject global context)
        3. Validate with dual-judge (hard + soft)
        4. Fallback to unpolished if polish fails

        Args:
            original_messages: Original trajectory messages
            ordered_tool_calls: Complete tool call sequence
            final_problem: User task description
            reference_answer: Reference answer for retrieval tasks
            task_type: "mutation" or "retrieval"
            expected_tool_steps: Number of tool calls
            prompt_bundle: Prompt templates

        Returns:
            Stage2TrajectoryResult with quality_tier="fallback_based"
        """
        realistic = False
        final_messages = original_messages
        trajectory_attempts = 0
        trajectory_accept_mode = "none"
        trajectory_last_failure_reason = ""
        quality_tier = ""
        hard_judge_pass = False
        soft_judge_pass = False
        soft_judge_score = 0.0
        soft_judge_issues: List[str] = []

        # Step 1: Generate rule-based fallback skeleton
        fallback_messages = self._build_structured_fallback_messages(
            messages=original_messages,
            ordered_tool_calls=ordered_tool_calls,
            problem=final_problem,
            reference_answer=reference_answer,
            task_type=task_type,
        )

        if not fallback_messages:
            logger.warning("Failed to generate fallback skeleton")
            return Stage2TrajectoryResult(
                realistic=False,
                final_messages=original_messages,
                attempts=0,
                accept_mode="fallback_skeleton_failed",
                last_failure_reason="Failed to generate fallback skeleton",
                quality_tier="",
                hard_judge_pass=False,
                soft_judge_pass=False,
                soft_judge_score=0.0,
                soft_judge_issues=[],
            )

        # Step 2: Polish skeleton with LLM
        max_polish_loops = getattr(self, "max_polish_loops", 3)
        critique = ""

        for attempt in range(1, max_polish_loops + 1):
            trajectory_attempts = attempt

            # Polish with full global context
            polished_messages = await self._polish_fallback_trajectory(
                fallback_messages=fallback_messages,
                ordered_tool_calls=ordered_tool_calls,
                problem=final_problem,
                reference_answer=reference_answer,
                task_type=task_type,
                require_plan=self.require_planning_step,
                require_final_answer=self.require_final_answer,
                critique=critique,
                prompt_bundle=prompt_bundle,
            )

            if not polished_messages:
                trajectory_last_failure_reason = "Polish failed to generate valid messages"
                logger.warning("Polish attempt %d failed", attempt)
                continue

            fallback_text = self._messages_to_text(polished_messages)

            # Step 3: Dual-judge validation in parallel (relaxed temperature for fallback path)
            (hard_ok, hard_reason), (soft_ok, soft_reason, soft_issues) = (
                await asyncio.gather(
                    self._judge_trajectory_hard(
                        final_problem,
                        fallback_text,
                        expected_tool_steps,
                        prompt_bundle,
                        task_type,
                        reference_answer,
                        use_relaxed=True,
                    ),
                    self._judge_trajectory_soft(
                        final_problem,
                        fallback_text,
                        expected_tool_steps,
                        prompt_bundle,
                        task_type,
                        use_relaxed=True,
                    ),
                )
            )

            if not hard_ok:
                trajectory_last_failure_reason = hard_reason
                critique = hard_reason
                logger.info("Polish attempt %d: hard judge rejected: %s", attempt, hard_reason)

                # Check for low-yield signals
                if self._is_trajectory_refine_low_yield(hard_reason):
                    logger.info("Low-yield failure detected, stopping polish loop")
                    break

                continue

            # Heuristic check (final gate)
            heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                polished_messages,
                expected_tool_steps,
                task_type=task_type,
                reference_answer=reference_answer,
                problem=final_problem,
                ordered_tool_calls=ordered_tool_calls,
            )

            if heuristic_ok:
                realistic = True
                final_messages = polished_messages
                trajectory_accept_mode = "fallback_polish_dual_judge_pass"
                hard_judge_pass = True
                soft_judge_pass = soft_ok
                soft_judge_issues = soft_issues
                quality_tier = "fallback_based"
                logger.info(
                    "Stage 2 accepted via fallback+polish (fallback_based): hard=%s, soft=%s, attempts=%d",
                    hard_ok,
                    soft_ok,
                    attempt,
                )
                break
            else:
                # Combine soft judge + heuristic feedback for next polish iteration
                critique_parts = []
                if not soft_ok and soft_reason:
                    critique_parts.append(f"[Style issues] {soft_reason}")
                    if soft_issues:
                        critique_parts.append("Specific issues: " + "; ".join(soft_issues))
                if heuristic_reason:
                    critique_parts.append(f"[Heuristic] {heuristic_reason}")
                critique = "\n".join(critique_parts) if critique_parts else heuristic_reason
                trajectory_last_failure_reason = heuristic_reason
                logger.info("Polish attempt %d: heuristic rejected: %s", attempt, heuristic_reason)

        # Step 4: Fallback to unpolished if polish fails
        if not realistic and self.enable_heuristic_fallback:
            logger.info("Polish failed, falling back to unpolished fallback skeleton")

            fallback_text = self._messages_to_text(fallback_messages)

            # Try dual-judge on unpolished fallback in parallel (relaxed temperature)
            (hard_ok, hard_reason), (soft_ok, soft_reason, soft_issues) = (
                await asyncio.gather(
                    self._judge_trajectory_hard(
                        final_problem,
                        fallback_text,
                        expected_tool_steps,
                        prompt_bundle,
                        task_type,
                        reference_answer,
                        use_relaxed=True,
                    ),
                    self._judge_trajectory_soft(
                        final_problem,
                        fallback_text,
                        expected_tool_steps,
                        prompt_bundle,
                        task_type,
                        use_relaxed=True,
                    ),
                )
            )

            if hard_ok:
                heuristic_ok, heuristic_reason = self._heuristic_trajectory_check(
                    fallback_messages,
                    expected_tool_steps,
                    task_type=task_type,
                    reference_answer=reference_answer,
                    problem=final_problem,
                    ordered_tool_calls=ordered_tool_calls,
                )

                if heuristic_ok:
                    realistic = True
                    final_messages = fallback_messages
                    trajectory_accept_mode = "fallback_unpolished_dual_judge_pass"
                    hard_judge_pass = True
                    soft_judge_pass = soft_ok
                    soft_judge_issues = soft_issues
                    quality_tier = "fallback_based"
                    logger.info(
                        "Stage 2 accepted via unpolished fallback (fallback_based): hard=%s, soft=%s",
                        hard_ok,
                        soft_ok,
                    )

        return Stage2TrajectoryResult(
            realistic=realistic,
            final_messages=final_messages,
            attempts=trajectory_attempts,
            accept_mode=trajectory_accept_mode,
            last_failure_reason=trajectory_last_failure_reason,
            quality_tier=quality_tier,
            hard_judge_pass=hard_judge_pass,
            soft_judge_pass=soft_judge_pass,
            soft_judge_score=soft_judge_score,
            soft_judge_issues=soft_judge_issues,
        )


