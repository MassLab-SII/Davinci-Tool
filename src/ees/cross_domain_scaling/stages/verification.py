from __future__ import annotations

from typing import Any

from ..models import Catalog
from ..runtime import CompositeRuntime
from .links import link_consistency_errors


def verify_trajectories(
    catalog: Catalog,
    manifests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for manifest in manifests:
        scenarios: list[dict[str, Any]] = []
        for scenario in manifest.get("scenarios", []):
            trajectory = scenario.get("trajectory")
            if trajectory is None:
                scenarios.append(dict(scenario))
                continue
            verification = _verify_one(catalog, manifest, scenario, trajectory)
            scenarios.append({**scenario, "verification": verification})
        enriched.append({**manifest, "scenarios": scenarios})
    return enriched


def _verify_one(
    catalog: Catalog,
    manifest: dict[str, Any],
    scenario: dict[str, Any],
    trajectory: dict[str, Any],
) -> dict[str, Any]:
    events = trajectory.get("events", [])
    runtime_errors = [event.get("error") for event in events if event.get("error")]
    failed_results = [
        event["index"]
        for event in events
        if _explicit_failure(event.get("result"))
    ]
    domains = {event.get("domain_id") for event in events if event.get("domain_id")}
    checks: list[dict[str, Any]] = [
        {
            "name": "runtime-execution",
            "passed": not runtime_errors and not failed_results,
            "evidence": {"errors": runtime_errors, "failed_event_indices": failed_results},
        },
        {
            "name": "cross-domain-execution",
            "passed": len(domains) >= 2,
            "evidence": {"invoked_domains": sorted(domains)},
        },
    ]
    for index, predicate in enumerate(scenario["predicates"]):
        passed, evidence = _evaluate_predicate(
            catalog, manifest, trajectory, predicate
        )
        checks.append(
            {
                "name": f"predicate-{index + 1:03d}",
                "kind": predicate["kind"],
                "passed": passed,
                "evidence": evidence,
            }
        )

    policies = {
        policy["id"]: policy for policy in manifest["world"]["cross_domain_policies"]
    }
    for policy_id in scenario.get("policy_ids", []):
        policy = policies.get(policy_id)
        if policy is None:
            checks.append(
                {
                    "name": f"policy:{policy_id}",
                    "passed": False,
                    "evidence": {"error": "unknown policy"},
                }
            )
            continue
        passed, evidence = _evaluate_predicate(
            catalog, manifest, trajectory, policy["predicate"]
        )
        checks.append(
            {
                "name": f"policy:{policy_id}",
                "passed": passed,
                "evidence": evidence,
            }
        )

    # Coherence constraints remain mandatory even when a task predicate omits one of the links.
    coherence_errors = _coherence_errors(catalog, manifest, trajectory["final_state"])
    checks.append(
        {
            "name": "coherence-constraints",
            "passed": not coherence_errors,
            "evidence": {"errors": coherence_errors},
        }
    )
    return {
        "accepted": all(check["passed"] for check in checks),
        "checks": checks,
        "outcome_evidence": {
            "initial_state": trajectory["initial_state"],
            "final_state": trajectory["final_state"],
            "tool_results": [event.get("result") for event in events],
            "final_response": trajectory.get("final_response", ""),
            "dependency_structure": scenario.get("dependencies", []),
            "transferred_entity_types": sorted(
                {
                    endpoint["entity"]
                    for dependency in scenario.get("dependencies", [])
                    for endpoint in (dependency["producer"], dependency["consumer"])
                }
            ),
        },
        "provenance": {
            "environment_id": manifest["id"],
            "scenario_id": scenario["id"],
            "rollout_mode": trajectory["mode"],
            "reset": scenario.get("reset_provenance", {}),
        },
    }


def _evaluate_predicate(
    catalog: Catalog,
    manifest: dict[str, Any],
    trajectory: dict[str, Any],
    predicate: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    events = trajectory["events"]
    kind = predicate["kind"]
    if kind == "tool_called":
        matching = [
            event["index"]
            for event in events
            if event.get("route") == predicate.get("route")
        ]
        return bool(matching), {"matching_event_indices": matching}
    if kind == "tool_order":
        before = [
            event["index"] for event in events if event.get("route") == predicate.get("before")
        ]
        after = [
            event["index"] for event in events if event.get("route") == predicate.get("after")
        ]
        passed = bool(before and after and min(before) < max(after))
        return passed, {"before_indices": before, "after_indices": after}
    if kind == "result_to_argument":
        producers = [
            event for event in events if event.get("route") == predicate.get("producer")
        ]
        consumers = [
            event for event in events if event.get("route") == predicate.get("consumer")
        ]
        argument_name = predicate.get("consumer_argument")
        matches: list[dict[str, Any]] = []
        for producer in producers:
            for consumer in consumers:
                value = consumer.get("arguments", {}).get(argument_name)
                if producer["index"] < consumer["index"] and _contains(
                    producer.get("result"), value
                ):
                    matches.append(
                        {
                            "producer_index": producer["index"],
                            "consumer_index": consumer["index"],
                            "value": value,
                        }
                    )
        return bool(matches), {"transfers": matches}
    if kind == "result_value":
        matches: list[int] = []
        for event in events:
            if event.get("route") != predicate.get("route"):
                continue
            found, value = _resolve_path(event.get("result"), predicate.get("path", []))
            if found and value == predicate.get("equals"):
                matches.append(event["index"])
        return bool(matches), {"matching_event_indices": matches}
    if kind == "state_changed":
        attribute = predicate.get("state_attribute")
        before = trajectory["initial_state"].get(attribute)
        after = trajectory["final_state"].get(attribute)
        return before != after, {"state_attribute": attribute, "before": before, "after": after}
    if kind == "link_preserved":
        link_id = predicate.get("link_id")
        errors = _coherence_errors(catalog, manifest, trajectory["final_state"], link_id)
        return not errors, {"link_id": link_id, "errors": errors}
    if kind == "state_value":
        attribute = predicate.get("state_attribute")
        found, value = _resolve_path(
            trajectory["final_state"].get(attribute), predicate.get("path", [])
        )
        return found and value == predicate.get("equals"), {
            "state_attribute": attribute,
            "found": found,
            "observed": value,
            "expected": predicate.get("equals"),
        }
    if kind == "final_response_contains":
        expected = str(predicate.get("text", ""))
        response = str(trajectory.get("final_response", ""))
        return expected.casefold() in response.casefold(), {
            "expected_text": expected,
            "final_response": response,
        }
    return False, {"error": f"unsupported predicate kind: {kind}"}


def _coherence_errors(
    catalog: Catalog,
    manifest: dict[str, Any],
    final_state: dict[str, Any],
    link_id: str | None = None,
) -> list[str]:
    links = manifest["world"]["entity_links"]
    if link_id is not None:
        links = [link for link in links if link["id"] == link_id]
        if not links:
            return [f"unknown link: {link_id}"]
    runtime = CompositeRuntime(catalog, manifest)
    runtime.restore(final_state)
    return link_consistency_errors(catalog, runtime, links, manifest["link_evidence"])


def _explicit_failure(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return result.get("ok") is False or result.get("success") is False


def _contains(container: Any, target: Any) -> bool:
    if container == target:
        return True
    if isinstance(container, dict):
        return any(_contains(value, target) for value in container.values())
    if isinstance(container, list):
        return any(_contains(value, target) for value in container)
    return False


def _resolve_path(value: Any, path: list[Any]) -> tuple[bool, Any]:
    current = value
    for part in path:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
            current = current[part]
        else:
            return False, None
    return True, current

