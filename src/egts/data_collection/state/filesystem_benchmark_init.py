"""Filesystem benchmark environment bootstrap for trajs2data.

This module discovers filesystem benchmark environments under one or more
benchmark roots (e.g. ../eval), deploys them into a workspace-local cache,
and provides init plans that copy a selected benchmark environment into the
current episode workspace.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import shutil
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_LOCAL_COPY_TOOL = "__local_copy_tree__"


@dataclass
class FilesystemBenchmarkEnvironment:
    """A discovered filesystem benchmark environment."""

    env_id: str
    kind: str  # "zip_url" | "local_dir"
    origin: str
    primary_source: str
    sources: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    materialized_path: Optional[str] = None

    def add_source(self, source: str) -> None:
        if source not in self.sources:
            self.sources.append(source)

    def add_reference(self, reference: str) -> None:
        if reference not in self.references:
            self.references.append(reference)

    def to_manifest_dict(self) -> dict:
        return {
            "env_id": self.env_id,
            "kind": self.kind,
            "origin": self.origin,
            "primary_source": self.primary_source,
            "sources": list(self.sources),
            "references": list(self.references),
            "materialized_path": self.materialized_path,
        }


@dataclass
class FilesystemBenchmarkInitPlan:
    """Init plan that copies a benchmark environment into episode workspace."""

    root: str
    seed: int
    env: FilesystemBenchmarkEnvironment

    def get_summary(self) -> dict:
        return {
            "root": self.root,
            "seed": self.seed,
            "init_mode": "benchmark",
            "benchmark_env_id": self.env.env_id,
            "benchmark_origin": self.env.origin,
            "benchmark_sources": self.env.sources,
            "total_operations": 1,
        }

    def to_operations(self) -> list[dict]:
        if not self.env.materialized_path:
            raise RuntimeError(
                f"Benchmark environment {self.env.env_id} has no materialized path"
            )

        return [
            {
                "tool": _LOCAL_COPY_TOOL,
                "arguments": {
                    "source": self.env.materialized_path,
                    "target": self.root,
                    "exclude": [".ready", "__MACOSX"],
                    "clean_target": False,
                },
            }
        ]


class FilesystemBenchmarkRepository:
    """Discover and deploy filesystem benchmark environments."""

    def __init__(
        self,
        benchmark_roots: list[str],
        workspace_root: str,
        cache_subdir: str = "benchmark_envs/filesystem",
        benchmark_source: str = "all",
        include_local_dirs: bool = True,
        download_timeout_sec: int = 900,
        max_environments: Optional[int] = None,
    ):
        self.benchmark_roots = [Path(p).resolve() for p in benchmark_roots]
        self.workspace_root = Path(workspace_root).resolve()
        self.cache_root = (self.workspace_root / cache_subdir).resolve()
        self.benchmark_source = benchmark_source or "all"
        self.include_local_dirs = include_local_dirs
        self.download_timeout_sec = max(10, int(download_timeout_sec))
        self.max_environments = max_environments

        self._environments: Optional[list[FilesystemBenchmarkEnvironment]] = None
        self._deployed = False

    def discover_environments(self) -> list[FilesystemBenchmarkEnvironment]:
        """Discover all available filesystem environments from benchmark roots."""
        if self._environments is not None:
            return self._environments

        url_envs: dict[str, FilesystemBenchmarkEnvironment] = {}
        local_envs: dict[str, FilesystemBenchmarkEnvironment] = {}

        for root in self.benchmark_roots:
            if not root.exists():
                logger.warning(f"Benchmark root does not exist: {root}")
                continue

            self._discover_from_meta_files(root, url_envs)
            if self.include_local_dirs:
                self._discover_local_dirs(root, local_envs)

        envs = list(url_envs.values()) + list(local_envs.values())
        envs = self._filter_by_source(envs)
        envs.sort(key=lambda e: (e.kind, e.env_id))

        if self.max_environments is not None:
            envs = envs[: self.max_environments]

        self._environments = envs
        logger.info(
            "Discovered %d filesystem benchmark environments (source=%s)",
            len(envs),
            self.benchmark_source,
        )
        return envs

    def deploy_all_environments(self) -> list[FilesystemBenchmarkEnvironment]:
        """Download/extract all discovered environments into cache."""
        envs = self.discover_environments()
        if self._deployed:
            return envs

        if not envs:
            logger.warning("No filesystem benchmark environments found to deploy")
            self._deployed = True
            return envs

        downloads_dir = self.cache_root / "downloads"
        extracted_dir = self.cache_root / "environments"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        extracted_dir.mkdir(parents=True, exist_ok=True)

        for env in envs:
            try:
                if env.kind == "zip_url":
                    zip_path = self._materialize_zip(env.origin, downloads_dir)
                    env_root = extracted_dir / env.env_id
                    self._extract_if_needed(zip_path, env_root)
                    env.materialized_path = str(env_root)
                else:
                    local_path = Path(env.origin).resolve()
                    if not local_path.exists():
                        logger.warning(
                            "Skipping missing local benchmark environment: %s",
                            local_path,
                        )
                        continue
                    env.materialized_path = str(local_path)
            except Exception as e:
                logger.warning(
                    "Failed to deploy benchmark environment %s (%s): %s",
                    env.env_id,
                    env.origin,
                    e,
                )

        self._write_manifest(envs)
        self._deployed = True

        ready_count = sum(1 for e in envs if e.materialized_path)
        logger.info(
            "Filesystem benchmark environments deployed: %d/%d at %s",
            ready_count,
            len(envs),
            self.cache_root,
        )
        return envs

    def pick_environment(self, seed: int) -> Optional[FilesystemBenchmarkEnvironment]:
        """Pick one available deployed environment deterministically by seed."""
        envs = self.deploy_all_environments()
        ready_envs = [
            e for e in envs if e.materialized_path and Path(e.materialized_path).exists()
        ]
        if not ready_envs:
            return None

        rng = random.Random(seed)
        return ready_envs[rng.randrange(len(ready_envs))]

    def create_init_plan(
        self, root: str, seed: int, env: FilesystemBenchmarkEnvironment
    ) -> FilesystemBenchmarkInitPlan:
        """Create a filesystem benchmark init plan for an episode workspace."""
        return FilesystemBenchmarkInitPlan(root=root, seed=seed, env=env)

    def _discover_from_meta_files(
        self,
        root: Path,
        url_envs: dict[str, FilesystemBenchmarkEnvironment],
    ) -> None:
        for meta_path in root.rglob("meta.json"):
            parts_lower = {p.lower() for p in meta_path.parts}
            if "filesystem" not in parts_lower:
                continue

            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue

            state_url = self._extract_state_url(data)
            if not state_url or not state_url.lower().endswith(".zip"):
                continue

            source = self._infer_source(root, meta_path)
            rel = self._safe_relpath(meta_path, root)

            env = url_envs.get(state_url)
            if env is None:
                env = FilesystemBenchmarkEnvironment(
                    env_id=self._build_env_id(Path(state_url.split("?")[0]).stem, state_url),
                    kind="zip_url",
                    origin=state_url,
                    primary_source=source,
                    sources=[source],
                )
                url_envs[state_url] = env

            env.add_source(source)
            env.add_reference(rel)

    def _discover_local_dirs(
        self,
        root: Path,
        local_envs: dict[str, FilesystemBenchmarkEnvironment],
    ) -> None:
        candidates: list[Path] = []

        # Common benchmark-local filesystem environment roots.
        targeted_roots = [
            root / "mcpverse/mcpverse/test_data/filesystem",
            root / "mcpmark/test_environments",
            root / "MCPEval/mcp_servers/filesystem",
        ]

        for candidate_root in targeted_roots:
            if candidate_root.exists() and candidate_root.is_dir():
                candidates.extend([p for p in candidate_root.iterdir() if p.is_dir()])

        # Fallback discovery for test_environments directories.
        for test_env_root in root.rglob("test_environments"):
            if not test_env_root.is_dir():
                continue
            candidates.extend([p for p in test_env_root.iterdir() if p.is_dir()])

        for local_dir in candidates:
            resolved = local_dir.resolve()
            key = str(resolved)
            if key in local_envs:
                continue

            source = self._infer_source(root, resolved)
            rel = self._safe_relpath(resolved, root)

            env = FilesystemBenchmarkEnvironment(
                env_id=self._build_env_id(resolved.name, key),
                kind="local_dir",
                origin=key,
                primary_source=source,
                sources=[source],
                references=[rel],
            )
            local_envs[key] = env

    def _filter_by_source(
        self, envs: list[FilesystemBenchmarkEnvironment]
    ) -> list[FilesystemBenchmarkEnvironment]:
        source = (self.benchmark_source or "all").strip().lower()
        if source in {"", "all", "*"}:
            return envs

        allowed = {s.strip().lower() for s in source.split(",") if s.strip()}
        if not allowed:
            return envs

        filtered = [
            e for e in envs if any(src.lower() in allowed for src in e.sources)
        ]

        if not filtered:
            logger.warning(
                "No environments match benchmark_source=%s; fallback to all",
                self.benchmark_source,
            )
            return envs

        return filtered

    @staticmethod
    def _extract_state_url(meta_data: dict) -> Optional[str]:
        nested = meta_data.get("meta_data", {})
        state_url = nested.get("stateUrl")
        if state_url:
            return str(state_url)

        state_url = meta_data.get("stateUrl")
        if state_url:
            return str(state_url)

        return None

    @staticmethod
    def _infer_source(root: Path, path: Path) -> str:
        rel = FilesystemBenchmarkRepository._safe_relpath(path, root)
        if rel == ".":
            return root.name
        return rel.split(os.sep, 1)[0]

    @staticmethod
    def _safe_relpath(path: Path, root: Path) -> str:
        try:
            return str(path.relative_to(root))
        except Exception:
            return str(path)

    @staticmethod
    def _build_env_id(name: str, unique_value: str) -> str:
        safe_name = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)
        safe_name = safe_name.strip("_") or "filesystem_env"
        digest = hashlib.sha1(unique_value.encode("utf-8")).hexdigest()[:10]
        return f"{safe_name}_{digest}"

    def _materialize_zip(self, url: str, downloads_dir: Path) -> Path:
        zip_name = f"{hashlib.sha1(url.encode('utf-8')).hexdigest()}.zip"
        zip_path = downloads_dir / zip_name
        tmp_path = downloads_dir / f"{zip_name}.part"

        if zip_path.exists() and zip_path.stat().st_size > 0:
            return zip_path

        logger.info("Downloading benchmark environment: %s", url)

        # Try urllib first with browser-like headers.
        urllib_error = None
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/123.0.0.0 Safari/537.36"
                    ),
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive",
                },
            )
            with urllib.request.urlopen(req, timeout=self.download_timeout_sec) as response:
                with tmp_path.open("wb") as out_file:
                    shutil.copyfileobj(response, out_file)
            tmp_path.replace(zip_path)
            return zip_path
        except Exception as e:
            urllib_error = e
            if tmp_path.exists():
                tmp_path.unlink()

        # Fallback to curl / wget, which may pass some CDN anti-bot checks better.
        cli_error = self._download_with_cli(url, tmp_path)
        if cli_error is None and tmp_path.exists() and tmp_path.stat().st_size > 0:
            tmp_path.replace(zip_path)
            return zip_path

        if tmp_path.exists():
            tmp_path.unlink()

        reason_parts = []
        if urllib_error is not None:
            reason_parts.append(f"urllib={urllib_error}")
        if cli_error is not None:
            reason_parts.append(f"cli={cli_error}")
        raise RuntimeError(
            "Failed to download benchmark zip: " + "; ".join(reason_parts)
        )

        return zip_path

    def _download_with_cli(self, url: str, output_path: Path) -> Optional[str]:
        """Try downloading with curl or wget."""
        curl_cmd = [
            "curl",
            "-fL",
            "--retry",
            "2",
            "--connect-timeout",
            "20",
            "-A",
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "-o",
            str(output_path),
            url,
        ]
        try:
            subprocess.run(
                curl_cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.download_timeout_sec,
            )
            return None
        except FileNotFoundError:
            pass
        except Exception as e:
            curl_err = str(e)
        else:
            curl_err = ""

        wget_cmd = [
            "wget",
            "-O",
            str(output_path),
            "--tries=2",
            "--timeout=20",
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            url,
        ]
        try:
            subprocess.run(
                wget_cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.download_timeout_sec,
            )
            return None
        except FileNotFoundError:
            if curl_err:
                return f"curl_failed={curl_err}; wget_not_found"
            return "curl_not_found; wget_not_found"
        except Exception as e:
            if curl_err:
                return f"curl_failed={curl_err}; wget_failed={e}"
            return f"wget_failed={e}"

    @staticmethod
    def _extract_if_needed(zip_path: Path, env_root: Path) -> None:
        ready_marker = env_root / ".ready"
        if ready_marker.exists():
            return

        if env_root.exists():
            shutil.rmtree(env_root)
        env_root.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.infolist():
                member_path = (env_root / member.filename).resolve()
                if not str(member_path).startswith(str(env_root.resolve())):
                    raise ValueError(f"Unsafe zip member path: {member.filename}")
            zip_ref.extractall(env_root)

        macosx_dir = env_root / "__MACOSX"
        if macosx_dir.exists():
            shutil.rmtree(macosx_dir)

        ready_marker.write_text("ready\n", encoding="utf-8")

    def _write_manifest(self, envs: list[FilesystemBenchmarkEnvironment]) -> None:
        manifest = {
            "benchmark_roots": [str(p) for p in self.benchmark_roots],
            "benchmark_source": self.benchmark_source,
            "cache_root": str(self.cache_root),
            "total_environments": len(envs),
            "ready_environments": sum(1 for e in envs if e.materialized_path),
            "environments": [e.to_manifest_dict() for e in envs],
        }

        manifest_path = self.cache_root / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
