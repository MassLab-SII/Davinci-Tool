from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .env_spec import ExecutableWorldEnvSpec


@dataclass(frozen=True)
class SelectedEnv:
    env: ExecutableWorldEnvSpec
    index: int


class ExecutableWorldEnvPool:
    """Deterministic env selector (round-robin).

    Designed to be concurrency-friendly: selection depends only on
    (iteration, worker_id), so workers won't contend on shared state.
    """

    def __init__(self, envs: List[ExecutableWorldEnvSpec]):
        if not envs:
            raise ValueError("ExecutableWorldEnvPool requires at least one env")
        self._envs = list(envs)

    @property
    def envs(self) -> List[ExecutableWorldEnvSpec]:
        return list(self._envs)

    def select(self, iteration: int, worker_id: int = 0) -> SelectedEnv:
        idx = (int(iteration) + int(worker_id)) % len(self._envs)
        return SelectedEnv(env=self._envs[idx], index=idx)

    def get_by_name(self, name: str) -> Optional[ExecutableWorldEnvSpec]:
        for e in self._envs:
            if e.name == name:
                return e
        return None


# Backward-compatible alias for older imports.
BenchmarkEnvPool = ExecutableWorldEnvPool
