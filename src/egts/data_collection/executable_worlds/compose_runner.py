from __future__ import annotations

import asyncio
import logging
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .env_spec import ExecutableWorldEnvSpec, HealthcheckSpec

logger = logging.getLogger(__name__)


@dataclass
class ComposeRunner:
    """Manage an executable world via docker compose.

    This runner is intentionally thin: it shells out to `docker compose`.
    """

    spec: ExecutableWorldEnvSpec
    worker_id: int = 0

    def _compose_args(self) -> list[str]:
        compose_file = str(Path(self.spec.compose_file))
        args = ["docker", "compose", "-f", compose_file]
        project = self._project_name()
        if project:
            args += ["-p", project]
        return args

    def _project_name(self) -> str:
        if self.spec.project_name:
            # Allow {worker_id} expansion
            return self.spec.project_name.format(worker_id=self.worker_id)
        return f"{self.spec.name}-w{self.worker_id}"

    async def ensure_started(self) -> None:
        # SSH tunnel mode: world is managed on a remote server.
        # Skip local docker compose — just verify healthcheck reachability.
        logger.info(f"[{self.spec.name}] SSH tunnel mode — skipping docker compose, waiting for health only")
        await self.wait_healthy()

    async def wait_healthy(self) -> None:
        await _wait_for_healthcheck(self.spec.healthcheck)

    async def reset(self) -> None:
        if not self.spec.reset_command:
            return
        # reset_command is executed on host.
        cmd = self.spec.reset_command.format(worker_id=self.worker_id)
        await self._run_shell(cmd, "env reset")

    async def stop(self) -> None:
        if self.spec.reuse_containers:
            return
        # SSH tunnel mode: world lifecycle is managed on the remote server.
        logger.info(f"[{self.spec.name}] SSH tunnel mode — skipping compose down")

    async def _run(self, cmd: list[str], label: str) -> None:
        logger.info(f"[{self.spec.name}] {label}: {' '.join(cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await proc.communicate()
        out = (out_b or b"").decode(errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"{label} failed (code {proc.returncode}):\n{out}")
        if out.strip():
            logger.debug(out)

    async def _run_shell(self, cmd: str, label: str) -> None:
        logger.info(f"[{self.spec.name}] {label}: {cmd}")
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out_b, _ = await proc.communicate()
        out = (out_b or b"").decode(errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(f"{label} failed (code {proc.returncode}):\n{out}")
        if out.strip():
            logger.debug(out)


async def _wait_for_healthcheck(spec: HealthcheckSpec) -> None:
    deadline = time.time() + float(spec.timeout_s)
    last_err: Optional[str] = None

    while time.time() < deadline:
        try:
            if spec.type == "command":
                # Execute command; non-zero means unhealthy.
                proc = await asyncio.create_subprocess_shell(
                    spec.value,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                rc = await proc.wait()
                if rc == 0:
                    return
                last_err = f"healthcheck command exited {rc}"

            elif spec.type == "url":
                # Avoid new deps (httpx/aiohttp). Use curl.
                url = spec.value
                cmd = [
                    "curl",
                    "-fsS",
                    "--max-time",
                    "2",
                    url,
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                rc = await proc.wait()
                if rc == 0:
                    return
                last_err = f"curl {url} exited {rc}"
            else:
                raise ValueError(f"Unknown healthcheck type: {spec.type}")

        except Exception as e:
            last_err = str(e)

        await asyncio.sleep(float(spec.interval_s))

    raise TimeoutError(
        f"Healthcheck timed out after {spec.timeout_s}s (type={spec.type}, value={spec.value}). "
        f"Last error: {last_err}"
    )
