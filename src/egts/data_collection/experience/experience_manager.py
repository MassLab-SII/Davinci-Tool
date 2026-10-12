"""Experience Manager orchestrator (PRD 4.7).

Main class that coordinates experience extraction, storage, and retrieval
to provide experience-based hints for exploration prompts.
"""

import asyncio
import copy
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from .experience_store import Experience, ExperienceStore
from .experience_extractor import ExperienceExtractor

logger = logging.getLogger(__name__)


class ExperienceManager:
    """Orchestrates experience extraction, storage, and retrieval.

    This class provides the main interface for the experience management
    system described in PRD 4.7. It:
    - Extracts experiences from successful trajectories
    - Stores experiences with deduplication
    - Retrieves relevant experience for exploration prompts
    """

    def __init__(self, config, maas_client, store_path: Path, model_config=None):
        """Initialize Experience Manager.

        Args:
            config: ExperienceConfig object
            maas_client: MaaS client for LLM calls
            store_path: Path to experience store file
            model_config: Optional model config for experience extraction
                         (defaults to nl_rewrite model if not provided)
        """
        self.config = config
        self.maas_client = maas_client
        self.model_config = model_config
        self.event_log_path = store_path.with_suffix(".events.jsonl")

        # Initialize experience store
        self.experience_store = ExperienceStore(
            store_path=store_path,
            max_experiences=getattr(config, "max_experiences", getattr(config, "max_skills", 100)),
            similarity_threshold=getattr(config, "similarity_threshold", 0.85),
        )

        # Initialize experience extractor
        self.experience_extractor = ExperienceExtractor(
            maas_client=maas_client, model_config=model_config
        )

        # Experience hint template
        self.experience_template = getattr(
            config, "experience_template",
            getattr(config, "skill_template", "\n[Relevant Experience]\n{experience}\n")
        )

        # Track in-flight background extraction tasks so flush() can await them.
        self._pending_tasks: set = set()

        logger.info(
            f"ExperienceManager initialized with {len(self.experience_store.get_all_experiences())} experiences"
        )

    async def _evolve_experience(self, new_exp: Experience) -> Optional[Experience]:
        """Evolve a new experience by attempting to merge it with existing similar experiences.

        This implements the 'Experience Evolution' concept from AgentEvolver:
        1. Retrieve similar existing experiences.
        2. Ask LLM to compare and decide: Merge/Refine or Keep Separate.
        3. If Merge, return the evolved experience.
        4. If Separate, return the original new experience.
        """
        candidates = self.experience_store.retrieve_experiences(
            query=new_exp.description + " " + new_exp.context_summary,
            top_k=3,
            required_tools=None,
            increment_retrieval_count=False,
        )

        if not candidates:
            return new_exp

        best_candidate = candidates[0]

        try:
            # Import templates here to avoid circular imports and ensure availability.
            try:
                from prompts.experience import (
                    EXPERIENCE_EVOLUTION_SYSTEM_PROMPT,
                    EXPERIENCE_EVOLUTION_USER_TEMPLATE,
                )
            except ImportError:
                # If templates are missing, skip evolution and keep the new experience.
                logger.warning(
                    "Experience evolution templates not found, skipping evolution step"
                )
                return new_exp

            user_prompt = EXPERIENCE_EVOLUTION_USER_TEMPLATE.format(
                existing_id=best_candidate.experience_id,
                existing_description=best_candidate.description,
                existing_context=best_candidate.context_summary,
                existing_action=best_candidate.action_sequence,
                new_description=new_exp.description,
                new_context=new_exp.context_summary,
                new_action=new_exp.action_sequence,
            )

            messages = [
                {"role": "system", "content": EXPERIENCE_EVOLUTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            response = await self.maas_client.generate_completion(
                messages=messages, model_config=self.model_config, tools=None
            )
            content = response.get("content", "")

            import re
            import json
            from datetime import datetime

            merged_match = re.search(
                r"<merged_experience>(.*?)</merged_experience>", content, re.DOTALL
            )
            if not merged_match:
                # Fallback: legacy tag
                merged_match = re.search(
                    r"<merged_skill>(.*?)</merged_skill>", content, re.DOTALL
                )
            if merged_match:
                try:
                    data = json.loads(merged_match.group(1).strip())
                    logger.info(
                        f"Experience Evolution: Merging {new_exp.experience_id} into {best_candidate.experience_id}. Reason: {data.get('reason')}"
                    )

                    best_candidate.description = data.get(
                        "experience_description",
                        data.get("skill_description", best_candidate.description)
                    )
                    best_candidate.context_summary = data.get(
                        "context_summary", best_candidate.context_summary
                    )
                    best_candidate.action_sequence = data.get(
                        "action_sequence", best_candidate.action_sequence
                    )

                    best_candidate.success_count += 1

                    best_candidate.last_used = datetime.now().isoformat()

                    self.experience_store.update_experience(best_candidate)

                    return None

                except json.JSONDecodeError:
                    logger.warning("Failed to parse merged experience JSON")

            logger.debug(f"Experience Evolution: Experiences kept separate.")
            return new_exp

        except Exception as e:
            logger.warning(f"Experience evolution failed: {e}")
            return new_exp

    async def on_episode_success(
        self,
        trajectory: Any,
        problem: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Experience]:
        """Called after successful episode - extract and store experience.

        Args:
            trajectory: The successful trajectory (StrictTrajectory or dict)
            problem: The synthesized problem dict

        Returns:
            The extracted Experience if successful, None otherwise
        """
        if not getattr(self.config, "extract_on_success", True):
            return None

        metadata = metadata or {}
        try:
            experience = await self.experience_extractor.extract_experience(
                trajectory, problem
            )

            if experience:
                experience.metadata.update(metadata)
                # Set source_namespace for namespace-scoped retrieval
                if not experience.source_namespace:
                    experience.source_namespace = (
                        metadata.get("output_namespace") or
                        metadata.get("data_source", {}).get("source_output_namespace")
                    )
                evolved_result = await self._evolve_experience(experience)

                if evolved_result:
                    is_new = self.experience_store.add_experience(evolved_result)
                    if is_new:
                        logger.info(f"New experience added: {experience.experience_id}")
                    # Always save after add_experience(): even when the
                    # experience was dedup'd (returns False), in-memory
                    # counters (success_count, last_used) were mutated and
                    # must be persisted.
                    self.experience_store.save()
                else:
                    # Evolution merged into an existing experience — persist
                    # the updated entry.
                    self.experience_store.save()

                self._record_event(
                    {
                        "event": "experience_extracted",
                        "experience_id": experience.experience_id,
                        "description": experience.description,
                        "tool_sequence": experience.tool_sequence,
                        "metadata": metadata,
                    }
                )
                return experience

            self._record_event(
                {
                    "event": "experience_skipped",
                    "reason": "extractor_returned_none",
                    "metadata": metadata,
                }
            )

        except Exception as e:
            logger.warning(f"Failed to extract experience on episode success: {e}")
            self._record_event(
                {
                    "event": "experience_failed",
                    "reason": str(e),
                    "metadata": metadata,
                }
            )

        return None

    def schedule_extraction(
        self,
        trajectory: Any,
        problem: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Schedule non-blocking experience extraction after episode success.

        Deep-copies inputs and runs ``on_episode_success()`` in a background
        asyncio task so the main collection loop is never blocked by the
        extraction/evolution LLM calls.

        Failures in the background task are logged but never propagated.

        Args:
            trajectory: The successful trajectory (will be deep-copied)
            problem: The synthesized problem dict (will be deep-copied)
            metadata: Optional metadata dict (will be deep-copied)
        """
        if not getattr(self.config, "extract_on_success", True):
            return

        # Deep-copy to decouple from caller's lifecycle
        try:
            traj_copy = copy.deepcopy(trajectory)
            prob_copy = copy.deepcopy(problem)
            meta_copy = copy.deepcopy(metadata) if metadata else {}
        except Exception as e:
            logger.warning(f"Failed to deep-copy for background extraction: {e}")
            return

        async def _background_extract():
            try:
                await self.on_episode_success(traj_copy, prob_copy, meta_copy)
            except Exception as e:
                logger.warning(f"Background experience extraction failed: {e}")
            finally:
                self._pending_tasks.discard(task)

        task = asyncio.create_task(_background_extract())
        self._pending_tasks.add(task)
        logger.debug("Scheduled background experience extraction")

    def _record_event(self, event: Dict[str, Any]) -> None:
        """Append an experience extraction event for auditability."""
        try:
            self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "timestamp": datetime.now().isoformat(),
                **event,
            }
            with open(self.event_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Failed to write experience event log: %s", exc)

    def get_experience_hints(
        self,
        context: str,
        tools: List[str],
        top_k: Optional[int] = None,
        preferred_tools: Optional[List[str]] = None,
        source_namespace: Optional[str] = None,
    ) -> str:
        """Retrieve relevant experience for exploration prompt.

        Args:
            context: Current context/task description
            tools: List of tool names being used
            top_k: Number of experiences to retrieve (default from config)
            preferred_tools: List of tools to prioritize in retrieval (e.g. underused ones)
            source_namespace: Namespace to scope experience retrieval to

        Returns:
            Formatted experience hints string to inject into prompt
        """
        if not getattr(self.config, "inject_to_prompt", True):
            return ""

        if top_k is None:
            top_k = getattr(self.config, "retrieve_top_k", 3)

        # Retrieve relevant experiences
        experiences = self.experience_store.retrieve_experiences(
            query=context,
            top_k=top_k,
            required_tools=tools if tools else None,
            boost_tools=preferred_tools,
            source_namespace=source_namespace,
            namespace_scoping_enabled=getattr(
                self.config, "namespace_scoping_enabled", False
            ),
        )

        if not experiences:
            self._record_event(
                {
                    "event": "experience_retrieval_empty",
                    "tools": tools,
                    "preferred_tools": preferred_tools or [],
                    "context_preview": context[:500],
                }
            )
            return ""

        # Format experiences into hints
        hints = []
        for exp in experiences:
            # Structured XML format for clearer context separation
            hint = f"<experience_item>\n  <description>{exp.description}</description>\n"
            if exp.action_sequence:
                hint += (
                    f"  <action_sequence>{exp.action_sequence}</action_sequence>\n"
                )
            elif exp.tool_sequence:
                # Fallback to tool sequence if action_sequence missing
                hint += f"  <action_sequence>{' -> '.join(exp.tool_sequence)}</action_sequence>\n"

            if exp.context_summary:
                hint += f"  <context>{exp.context_summary}</context>\n"

            if hasattr(exp, "confidence") and exp.confidence < 1.0:
                hint += f"  <confidence>{exp.confidence}</confidence>\n"

            hint += f"</experience_item>"
            hints.append(hint)

        self._record_event(
            {
                "event": "experience_retrieved",
                "experience_ids": [e.experience_id for e in experiences],
                "tools": tools,
                "preferred_tools": preferred_tools or [],
                "context_preview": context[:500],
            }
        )

        hints_text = "\n".join(hints)

        # Apply template
        return self.experience_template.format(experience=hints_text)

    def get_stats(self) -> Dict[str, Any]:
        """Get experience manager statistics."""
        return self.experience_store.get_stats()

    def save(self):
        """Persist experience store to disk."""
        self.experience_store.save()

    async def flush(self) -> int:
        """Await all in-flight background extractions and persist the store.

        Call this at experiment shutdown so that fire-and-forget extraction
        tasks started by ``schedule_extraction()`` are given a chance to
        finish before the process exits.  Any new tasks that are scheduled
        while waiting will also be drained.

        Returns:
            Number of background tasks that were awaited.
        """
        waited = 0
        while self._pending_tasks:
            batch = list(self._pending_tasks)
            logger.info(
                "ExperienceManager.flush: waiting for %d pending extraction(s)…",
                len(batch),
            )
            for task in batch:
                try:
                    await task
                    waited += 1
                except Exception as e:
                    logger.warning("Background extraction task failed: %s", e)

        # Final persist — covers any in-memory mutations from completed tasks.
        self.save()
        logger.info(
            "ExperienceManager.flush complete: %d task(s) awaited, store saved.", waited
        )
        return waited

    def get_all_experiences(self) -> List[Experience]:
        """Get all stored experiences."""
        return self.experience_store.get_all_experiences()


def create_experience_manager(
    config, maas_client, output_dir: Path, model_config=None
) -> Optional[ExperienceManager]:
    """Factory function to create ExperienceManager if enabled.

    Args:
        config: Trajs2DataConfig object
        maas_client: MaaS client
        output_dir: Output directory for experience store
        model_config: Optional model config

    Returns:
        ExperienceManager if enabled, None otherwise
    """
    exp_config = getattr(config, "experience_manager", None)

    if exp_config is None or not getattr(exp_config, "enabled", False):
        return None

    store_path = output_dir / getattr(exp_config, "store_path", "experience_store.json")

    return ExperienceManager(
        config=exp_config,
        maas_client=maas_client,
        store_path=store_path,
        model_config=model_config,
    )
