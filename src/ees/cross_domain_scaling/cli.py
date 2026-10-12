from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .config import ProviderSettings
from .llm import OpenAICompatibleGenerator
from .models import Catalog, CatalogError
from .pipeline import BuildOptions, build_bundle
from .runtime import CompositeRuntime
from .storage import read_json, write_json


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        return arguments.handler(arguments)
    except (CatalogError, FileNotFoundError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cross-domain-scaling",
        description="Build and run portable multi-domain tool environments.",
    )
    parser.add_argument("--version", action="version", version="cross-domain-scaling 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate a domain catalog")
    validate.add_argument("catalog", type=Path)
    validate.set_defaults(handler=_validate)

    build = commands.add_parser("build", help="build a reproducible environment bundle")
    build.add_argument("catalog", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--count", type=int, default=25)
    build.add_argument("--min-domains", type=int, default=2)
    build.add_argument("--max-domains", type=int, default=4)
    build.add_argument("--seed", type=int, default=0)
    build.add_argument("--neighbors", type=int, default=6)
    build.add_argument("--affinity-threshold", type=float, default=0.03)
    build.add_argument("--affinity-mode", choices=("contract", "semantic"), default="contract")
    build.add_argument("--context-mode", choices=("offline", "llm"), default="offline")
    build.add_argument("--judge-mode", choices=("none", "llm"), default="none")
    build.add_argument("--scenarios-per-environment", type=int, default=0)
    build.add_argument("--scenario-mode", choices=("offline", "llm"), default="offline")
    build.add_argument("--rollout-mode", choices=("none", "reference", "llm"), default="none")
    build.add_argument("--max-steps", type=int, default=12)
    build.set_defaults(handler=_build)

    inspect = commands.add_parser("inspect", help="print a bundle summary")
    inspect.add_argument("bundle", type=Path)
    inspect.set_defaults(handler=_inspect)

    invoke = commands.add_parser("invoke", help="invoke one routed operation")
    invoke.add_argument("bundle", type=Path)
    invoke.add_argument("environment_id")
    invoke.add_argument("route")
    invoke.add_argument("arguments", help="operation arguments as a JSON object")
    invoke.set_defaults(handler=_invoke)
    return parser


def _load_catalog(path: Path) -> Catalog:
    return Catalog.from_data(read_json(path))


def _validate(arguments: argparse.Namespace) -> int:
    catalog = _load_catalog(arguments.catalog)
    for domain in catalog.domains:
        alias = domain.id.replace("-", "_")
        routes = {
            f"{alias}__{operation.name}": {
                "domain_id": domain.id,
                "operation": operation.name,
            }
            for operation in domain.operations
        }
        CompositeRuntime(catalog, {"domain_ids": [domain.id], "routes": routes})
    operations = sum(len(domain.operations) for domain in catalog.domains)
    print(f"valid catalog: {len(catalog.domains)} domains, {operations} operations")
    return 0


def _build(arguments: argparse.Namespace) -> int:
    catalog = _load_catalog(arguments.catalog)
    options = BuildOptions(
        count=arguments.count,
        minimum_domains=arguments.min_domains,
        maximum_domains=arguments.max_domains,
        seed=arguments.seed,
        neighbors_per_domain=arguments.neighbors,
        affinity_threshold=arguments.affinity_threshold,
        affinity_mode=arguments.affinity_mode,
        context_mode=arguments.context_mode,
        judge_mode=arguments.judge_mode,
        scenarios_per_environment=arguments.scenarios_per_environment,
        scenario_mode=arguments.scenario_mode,
        rollout_mode=arguments.rollout_mode,
        max_steps=arguments.max_steps,
    )
    generator = None
    if (
        arguments.affinity_mode == "semantic"
        or arguments.context_mode == "llm"
        or arguments.judge_mode == "llm"
        or (arguments.scenarios_per_environment > 0 and arguments.scenario_mode == "llm")
        or (arguments.scenarios_per_environment > 0 and arguments.rollout_mode == "llm")
    ):
        generator = OpenAICompatibleGenerator(ProviderSettings.from_environment())
    bundle = build_bundle(catalog, options, generator=generator, embedder=generator)
    target = arguments.output / "bundle.json"
    write_json(target, bundle)
    summary = bundle["summary"]
    print(
        f"wrote {target} ({summary['accepted_environments']}/"
        f"{summary['generated_environments']} environments accepted, "
        f"{summary['verified_trajectories']} trajectories verified)"
    )
    return 0


def _inspect(arguments: argparse.Namespace) -> int:
    bundle = _load_bundle(arguments.bundle)
    view = {
        "schema_version": bundle.get("schema_version"),
        "build": bundle.get("build"),
        "summary": bundle.get("summary"),
        "environment_ids": [item.get("id") for item in bundle.get("environments", [])],
    }
    print(json.dumps(view, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _invoke(arguments: argparse.Namespace) -> int:
    bundle = _load_bundle(arguments.bundle)
    try:
        operation_arguments = json.loads(arguments.arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("arguments must be valid JSON") from exc
    if not isinstance(operation_arguments, dict):
        raise ValueError("arguments must be a JSON object")

    environments = bundle.get("environments", [])
    manifest = next(
        (item for item in environments if item.get("id") == arguments.environment_id), None
    )
    if manifest is None:
        raise ValueError(f"unknown environment id: {arguments.environment_id}")
    catalog = Catalog.from_data(bundle.get("catalog"))
    runtime = CompositeRuntime(catalog, manifest)
    result = runtime.invoke(arguments.route, operation_arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))
    return 0


def _load_bundle(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, dict) or value.get("generator") != "cross-domain-scaling":
        raise ValueError(f"{path} is not a cross-domain-scaling bundle")
    return value


def _json_default(value: Any) -> str:
    return repr(value)

