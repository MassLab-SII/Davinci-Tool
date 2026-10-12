from __future__ import annotations

import json
from typing import Any

from ..llm import JsonGenerator
from ..models import Catalog
from ..runtime import CompositeRuntime


def collect_trajectories(
    catalog: Catalog,
    manifests: list[dict[str, Any]],
    *,
    mode: str,
    generator: JsonGenerator | None,
    max_steps: int,
) -> list[dict[str, Any]]:
    if mode not in {"none", "reference", "llm"}:
        raise ValueError("rollout mode must be 'none', 'reference', or 'llm'")
    if mode == "llm" and generator is None:
        raise ValueError("LLM rollout mode requires a configured generator")
    if max_steps < 1:
        raise ValueError("max_steps must be positive")

    enriched: list[dict[str, Any]] = []
    for manifest in manifests:
        scenarios: list[dict[str, Any]] = []
        for scenario in manifest.get("scenarios", []):
            if mode == "none":
                scenarios.append(dict(scenario))
                continue
            trajectory = _run_scenario(
                catalog,
                manifest,
                scenario,
                mode=mode,
                generator=generator,
                max_steps=max_steps,
            )
            scenarios.append({**scenario, "trajectory": trajectory})
        enriched.append({**manifest, "scenarios": scenarios})
    return enriched


def _run_scenario(
    catalog: Catalog,
    manifest: dict[str, Any],
    scenario: dict[str, Any],
    *,
    mode: str,
    generator: JsonGenerator | None,
    max_steps: int,
) -> dict[str, Any]:
    runtime = CompositeRuntime(catalog, manifest)
    runtime.restore(scenario["reset_state"])
    runtime.commit_initial_state()
    initial_state = runtime.snapshot()
    events: list[dict[str, Any]] = []
    final_response = ""

    if mode == "reference":
        for action in scenario["reference_plan"][:max_steps]:
            event = _execute(runtime, manifest, len(events) + 1, action)
            events.append(event)
            if event.get("error"):
                break
        final_response = "The requested cross-domain workflow was executed."
    else:
        assert generator is not None
        for _ in range(max_steps):
            decision = _model_decision(generator, manifest, scenario, events, runtime.snapshot())
            decision_type = decision.get("type")
            if decision_type == "final":
                final_response = str(decision.get("response", ""))
                break
            if decision_type != "tool":
                events.append(
                    {
                        "index": len(events) + 1,
                        "error": "model decision type must be 'tool' or 'final'",
                    }
                )
                break
            event = _execute(
                runtime,
                manifest,
                len(events) + 1,
                {"route": decision.get("route"), "arguments": decision.get("arguments", {})},
            )
            events.append(event)
            if event.get("error"):
                break
        else:
            final_response = "Maximum tool-call budget reached."

    return {
        "mode": mode,
        "initial_state": initial_state,
        "events": events,
        "final_state": runtime.snapshot(),
        "final_response": final_response,
    }


def _execute(
    runtime: CompositeRuntime,
    manifest: dict[str, Any],
    index: int,
    action: dict[str, Any],
) -> dict[str, Any]:
    route = action.get("route")
    arguments = action.get("arguments", {})
    before = runtime.snapshot()
    event: dict[str, Any] = {
        "index": index,
        "route": route,
        "domain_id": manifest.get("routes", {}).get(route, {}).get("domain_id"),
        "arguments": arguments,
        "state_before": before,
    }
    if route not in manifest["routes"]:
        event["error"] = f"unknown route: {route}"
        event["state_after"] = before
        return event
    if not isinstance(arguments, dict):
        event["error"] = "tool arguments must be an object"
        event["state_after"] = before
        return event
    try:
        event["result"] = runtime.invoke(route, arguments)
    except Exception as exc:
        event["error"] = f"{type(exc).__name__}: {exc}"
    event["state_after"] = runtime.snapshot()
    return event


def _model_decision(
    generator: JsonGenerator,
    manifest: dict[str, Any],
    scenario: dict[str, Any],
    events: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    visible_history = [
        {
            "route": event.get("route"),
            "arguments": event.get("arguments"),
            "result": event.get("result"),
            "error": event.get("error"),
        }
        for event in events
    ]
    return generator.generate(
        system=(
            "Solve the user task by calling only declared routes. Read relevant state before "
            "mutations and preserve cross-domain policies. Return JSON with either "
            "{type:'tool', route:string, arguments:object} or "
            "{type:'final', response:string}."
        ),
        prompt=json.dumps(
            {
                "task": scenario["task"],
                "role": scenario["role"],
                "world": manifest["world"],
                "tools": manifest["tools"],
                "current_state": state,
                "history": visible_history,
            },
            ensure_ascii=False,
            default=repr,
        ),
    )

