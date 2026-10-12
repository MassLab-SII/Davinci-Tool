"""Executable-world session abstraction for EGTS collection."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from .context import build_world_context

logger = logging.getLogger(__name__)


@dataclass
class WorldResetResult:
    """Result of resetting an executable world."""

    strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)
    initial_state: Any = None
    init_plan: Any = None
    init_results: list[dict[str, Any]] = field(default_factory=list)


class WorldStateHashDiff:
    """Diff-like object for admin-managed worlds that expose state hashes."""

    def __init__(self, changed: bool, s0: dict[str, Any], s1: dict[str, Any]):
        self.changed = bool(changed)
        self.s0 = s0
        self.s1 = s1

    def is_empty(self) -> bool:
        return not self.changed

    def total_changes(self) -> int:
        return 1 if self.changed else 0

    def get_change_summary(self) -> str:
        if self.changed:
            return f"World state changed (S0={self.s0}, S1={self.s1})"
        return "World state unchanged"


class ExecutableWorldSession:
    """Unified reset/snapshot/diff facade over adapter and admin worlds.

    This class is deliberately thin: service-specific mechanics stay in
    adapters/admin endpoints, while the collection pipeline can interact with a
    common world session contract.
    """

    def __init__(
        self,
        *,
        task_config: Any,
        primary_server: str,
        prompt_domain: str,
        output_namespace: str,
        mcp_client: Any,
        adapters: dict[str, Any],
        root: str | Path,
        build_init_plan: Callable[[Any, Any, str], Any],
        execute_init_plan: Callable[[Any, Any], Awaitable[list[dict[str, Any]]]],
        snapshot_provider_factory: Optional[Callable[[Any, Any, str], Any]] = None,
    ):
        self.task_config = task_config
        self.primary_server = primary_server
        self.prompt_domain = prompt_domain
        self.output_namespace = output_namespace
        self.mcp_client = mcp_client
        self.adapters = adapters or {}
        self.root = str(root)
        self.build_init_plan = build_init_plan
        self.execute_init_plan = execute_init_plan
        self.snapshot_provider_factory = snapshot_provider_factory

        self.reset_strategy = "none"
        self.state_strategy = "none"
        self.reset_metadata: dict[str, Any] = {}
        self.init_plan: Any = None
        self.snapshot_provider: Any = None
        self.initial_state: Any = None

    async def reset(
        self,
        *,
        seed: int,
        reset_body: Optional[dict[str, Any]] = None,
    ) -> WorldResetResult:
        """Reset the executable world and capture its initial state when possible."""
        if self.adapters and "init_generator" in self.adapters:
            return await self._reset_adapter_world(seed=seed)

        if hasattr(self.mcp_client, "admin_request"):
            return await self._reset_admin_world(seed=seed, reset_body=reset_body or {})

        self.reset_strategy = "none"
        self.state_strategy = "none"
        return WorldResetResult(strategy="none")

    async def _reset_adapter_world(self, *, seed: int) -> WorldResetResult:
        self.reset_strategy = "adapter_init_plan"
        init_generator_class = self.adapters["init_generator"]
        init_generator = init_generator_class(seed=seed)
        init_plan = self.build_init_plan(self.task_config, init_generator, self.root)
        init_results = await self.execute_init_plan(init_plan, self.mcp_client)
        self.init_plan = init_plan

        init_summary = (
            init_plan.get_summary()
            if hasattr(init_plan, "get_summary") and callable(init_plan.get_summary)
            else {}
        )
        self.reset_metadata = {"init_summary": init_summary}

        if "snapshot_provider" in self.adapters:
            self.state_strategy = "adapter_snapshot_diff"
            snapshot_provider_class = self.adapters["snapshot_provider"]
            if self.snapshot_provider_factory is not None:
                self.snapshot_provider = self.snapshot_provider_factory(
                    snapshot_provider_class,
                    self.mcp_client,
                    self.root,
                )
            else:
                self.snapshot_provider = snapshot_provider_class(
                    mcp_client=self.mcp_client,
                    root=self.root,
                )
            self.initial_state = await self.snapshot_provider.create_snapshot(self.root)

        return WorldResetResult(
            strategy=self.reset_strategy,
            metadata=self.reset_metadata,
            initial_state=self.initial_state,
            init_plan=init_plan,
            init_results=init_results,
        )

    async def _reset_admin_world(
        self,
        *,
        seed: int,
        reset_body: dict[str, Any],
    ) -> WorldResetResult:
        self.reset_strategy = "admin_reset"
        body = dict(reset_body)
        body.setdefault("seed", seed)

        reset_meta = await self.mcp_client.admin_request(
            "/admin/reset", method="POST", body=body
        )
        self.reset_metadata = reset_meta if isinstance(reset_meta, dict) else {}

        try:
            self.initial_state = await self.mcp_client.admin_request("/admin/state")
            self.state_strategy = "admin_state_hash"
        except Exception as exc:
            logger.warning("Could not capture admin world initial state: %s", exc)
            self.state_strategy = "none"

        return WorldResetResult(
            strategy=self.reset_strategy,
            metadata=self.reset_metadata,
            initial_state=self.initial_state,
        )

    async def diff_from_initial(self) -> Any:
        """Compute state evidence from the last reset state to current state."""
        if (
            self.snapshot_provider is not None
            and self.initial_state is not None
            and "diff_comparator" in self.adapters
        ):
            snapshot_s1 = await self.snapshot_provider.create_snapshot(self.root)
            diff_comparator_class = self.adapters["diff_comparator"]
            diff_comparator = diff_comparator_class()
            return diff_comparator.diff(self.initial_state, snapshot_s1)

        if (
            hasattr(self.mcp_client, "admin_request")
            and isinstance(self.initial_state, dict)
        ):
            state_s1 = await self.mcp_client.admin_request("/admin/state")
            s0_hash = (
                self.initial_state.get("agent_db_hash"),
                self.initial_state.get("user_db_hash"),
            )
            s1_hash = (
                state_s1.get("agent_db_hash"),
                state_s1.get("user_db_hash"),
            )
            return WorldStateHashDiff(changed=s0_hash != s1_hash, s0=self.initial_state, s1=state_s1)

        return None

    def context(self) -> dict[str, Any]:
        """Return canonical executable-world context for metadata/raw context."""
        return build_world_context(
            task_config=self.task_config,
            primary_server=self.primary_server,
            prompt_domain=self.prompt_domain,
            output_namespace=self.output_namespace,
            reset_strategy=self.reset_strategy,
            state_strategy=self.state_strategy,
            reset_metadata=self.reset_metadata,
        )
