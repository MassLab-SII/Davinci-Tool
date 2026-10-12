from __future__ import annotations

import json
from typing import Any

from ..llm import JsonGenerator
from ..models import Catalog, OperationSpec

_PREDICATE_KINDS = {
    "final_response_contains",
    "link_preserved",
    "result_value",
    "result_to_argument",
    "state_changed",
    "state_value",
    "tool_called",
    "tool_order",
}


def attach_scenarios(
    catalog: Catalog,
    manifests: list[dict[str, Any]],
    *,
    count: int,
    mode: str,
    generator: JsonGenerator | None,
) -> list[dict[str, Any]]:
    if count < 0:
        raise ValueError("scenario count cannot be negative")
    if mode not in {"offline", "llm"}:
        raise ValueError("scenario mode must be 'offline' or 'llm'")
    if mode == "llm" and generator is None:
        raise ValueError("LLM scenario mode requires a configured generator")

    enriched: list[dict[str, Any]] = []
    for manifest in manifests:
        if count == 0 or not manifest["validation"]["accepted"]:
            enriched.append({**manifest, "scenarios": []})
            continue
        if mode == "offline":
            scenarios = _offline_scenarios(catalog, manifest, count)
        else:
            assert generator is not None
            scenarios = _llm_scenarios(catalog, manifest, count, generator)
        enriched.append({**manifest, "scenarios": scenarios})
    return enriched


def _offline_scenarios(
    catalog: Catalog,
    manifest: dict[str, Any],
    count: int,
) -> list[dict[str, Any]]:
    known = catalog.by_id()
    evidence = {item["link_id"]: item for item in manifest["link_evidence"]}
    values = _named_values(manifest["initial_state"])
    candidates: list[dict[str, Any]] = []
    for link in manifest["world"]["entity_links"]:
        for producer_ref, consumer_ref in (
            (link["left"], link["right"]),
            (link["right"], link["left"]),
        ):
            producer_domain = known[producer_ref["domain_id"]]
            consumer_domain = known[consumer_ref["domain_id"]]
            producer_ops = [
                operation
                for operation in producer_domain.operations
                if operation.mode == "read" and producer_ref["field"] in operation.result_fields
            ]
            consumer_ops = [
                operation
                for operation in consumer_domain.operations
                if operation.mode == "write"
                and consumer_ref["field"] in operation.parameters.get("properties", {})
            ]
            for producer in producer_ops:
                for consumer in consumer_ops:
                    candidates.append(
                        _scenario_from_pair(
                            manifest,
                            producer_ref,
                            consumer_ref,
                            producer,
                            consumer,
                            evidence[link["id"]]["value"],
                            values,
                            link,
                        )
                    )

    scenarios: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates[:count], start=1):
        candidate["id"] = f"{manifest['id']}-scenario-{index:03d}"
        _validate_scenario(manifest, candidate)
        scenarios.append(candidate)
    return scenarios


def _scenario_from_pair(
    manifest: dict[str, Any],
    producer_ref: dict[str, str],
    consumer_ref: dict[str, str],
    producer: OperationSpec,
    consumer: OperationSpec,
    linked_value: Any,
    values: dict[str, list[Any]],
    link: dict[str, Any],
) -> dict[str, Any]:
    producer_route = manifest["namespace"][producer_ref["domain_id"]]["tools"][producer.name]
    consumer_route = manifest["namespace"][consumer_ref["domain_id"]]["tools"][consumer.name]
    producer_overrides = (
        {producer_ref["field"]: linked_value}
        if producer_ref["field"] in producer.parameters.get("properties", {})
        else {}
    )
    consumer_overrides = {consumer_ref["field"]: linked_value}
    producer_arguments = _operation_arguments(producer, values, producer_overrides)
    consumer_arguments = _operation_arguments(consumer, values, consumer_overrides)
    consumer_state = next(
        iter(
            manifest["namespace"][consumer_ref["domain_id"]]["state_attributes"].values()
        ),
        None,
    )
    predicates: list[dict[str, Any]] = [
        {"kind": "tool_called", "route": producer_route},
        {"kind": "tool_called", "route": consumer_route},
        {"kind": "tool_order", "before": producer_route, "after": consumer_route},
        {
            "kind": "result_to_argument",
            "producer": producer_route,
            "consumer": consumer_route,
            "consumer_argument": consumer_ref["field"],
        },
        {"kind": "link_preserved", "link_id": link["id"]},
    ]
    if consumer_state is not None:
        predicates.append({"kind": "state_changed", "state_attribute": consumer_state})
    return {
        "id": "pending",
        "task": (
            f"Confirm the current {producer_ref['entity']} identified by "
            f"{producer_ref['field']}={linked_value!r}, then complete the required "
            f"{consumer.name.replace('_', ' ')} action in the connected "
            "system while preserving cross-domain consistency."
        ),
        "role": manifest["world"]["roles"][0]["name"],
        "required_domains": [producer_ref["domain_id"], consumer_ref["domain_id"]],
        "policy_ids": [
            policy["id"]
            for policy in manifest["world"]["cross_domain_policies"]
            if set(policy["domains"])
            == {producer_ref["domain_id"], consumer_ref["domain_id"]}
        ],
        "dependencies": [
            {
                "type": "entity_transfer",
                "link_id": link["id"],
                "producer": {
                    "domain_id": producer_ref["domain_id"],
                    "entity": producer_ref["entity"],
                    "field": producer_ref["field"],
                },
                "consumer": {
                    "domain_id": consumer_ref["domain_id"],
                    "entity": consumer_ref["entity"],
                    "field": consumer_ref["field"],
                },
            }
        ],
        "reference_plan": [
            {"route": producer_route, "arguments": producer_arguments},
            {"route": consumer_route, "arguments": consumer_arguments},
        ],
        "predicates": predicates,
        "reset_state": manifest["initial_state"],
        "reset_provenance": {
            "source": "linked-environment-initial-state",
            "environment_id": manifest["id"],
            "link_ids": [link["id"]],
        },
        "generation": "offline",
    }


def _operation_arguments(
    operation: OperationSpec,
    values: dict[str, list[Any]],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    properties = operation.parameters.get("properties", {})
    required = operation.parameters.get("required", [])
    selected = set(required) | (set(overrides) & set(properties))
    arguments: dict[str, Any] = {}
    for name in selected:
        if name in overrides:
            arguments[name] = overrides[name]
        elif values.get(name):
            arguments[name] = values[name][0]
        else:
            arguments[name] = _placeholder(properties.get(name, {}))
    return arguments


def _placeholder(schema: Any) -> Any:
    kind = schema.get("type") if isinstance(schema, dict) else None
    if kind == "integer":
        return max(1, int(schema.get("minimum", 1)))
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return True
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return "example"


def _named_values(value: Any) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(child, (dict, list)):
                    result.setdefault(str(key), []).append(child)
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return result


def _llm_scenarios(
    catalog: Catalog,
    manifest: dict[str, Any],
    count: int,
    generator: JsonGenerator,
) -> list[dict[str, Any]]:
    known = catalog.by_id()
    prompt = {
        "count": count,
        "domains": [known[domain_id].to_dict() for domain_id in manifest["domain_ids"]],
        "world": manifest["world"],
        "initial_state": manifest["initial_state"],
        "routes": manifest["routes"],
        "tools": manifest["tools"],
        "allowed_predicates": sorted(_PREDICATE_KINDS),
        "required_output": {
            "scenarios": [
                {
                    "task": "natural user request without revealing the action plan",
                    "role": "one declared role",
                    "required_domains": ["at least two domain ids"],
                    "policy_ids": ["applicable policy ids"],
                    "dependencies": [
                        {
                            "type": "entity_transfer",
                            "link_id": "declared link id",
                            "producer": {
                                "domain_id": "string",
                                "entity": "string",
                                "field": "string",
                            },
                            "consumer": {
                                "domain_id": "string",
                                "entity": "string",
                                "field": "string",
                            },
                        }
                    ],
                    "reference_plan": [
                        {"route": "declared route", "arguments": {"parameter": "value"}}
                    ],
                    "predicates": [{"kind": "allowed predicate", "...": "kind fields"}],
                }
            ]
        },
    }
    result = generator.generate(
        system=(
            "Generate state-grounded cross-domain tasks. Every task must require operations from "
            "at least two domains and an explicit entity transfer, operation order, or "
            "cross-domain policy dependency. Reference plans are private construction evidence "
            "and must not be revealed in task text. Return one JSON object."
        ),
        prompt=json.dumps(prompt, ensure_ascii=False),
    )
    raw = result.get("scenarios")
    if not isinstance(raw, list):
        raise ValueError("scenario generator must return a scenarios array")
    scenarios: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:count], start=1):
        if not isinstance(item, dict):
            raise ValueError("each generated scenario must be an object")
        scenario = {
            **item,
            "id": f"{manifest['id']}-scenario-{index:03d}",
            "reset_state": manifest["initial_state"],
            "reset_provenance": {
                "source": "linked-environment-initial-state",
                "environment_id": manifest["id"],
                "link_ids": [link["id"] for link in manifest["world"]["entity_links"]],
            },
            "generation": "llm",
        }
        _validate_scenario(manifest, scenario)
        scenarios.append(scenario)
    return scenarios


def _validate_scenario(manifest: dict[str, Any], scenario: dict[str, Any]) -> None:
    if not isinstance(scenario.get("task"), str) or not scenario["task"].strip():
        raise ValueError("scenario task must be a non-empty string")
    domains = scenario.get("required_domains")
    if not isinstance(domains, list) or len(set(domains)) < 2:
        raise ValueError("a cross-domain scenario must require at least two domains")
    if not set(domains).issubset(set(manifest["domain_ids"])):
        raise ValueError("scenario references a domain outside its environment")
    known_policies = {
        policy["id"] for policy in manifest["world"]["cross_domain_policies"]
    }
    policy_ids = scenario.get("policy_ids", [])
    if not isinstance(policy_ids, list) or not set(policy_ids).issubset(known_policies):
        raise ValueError("scenario references an unknown cross-domain policy")
    dependencies = scenario.get("dependencies")
    known_links = {link["id"]: link for link in manifest["world"]["entity_links"]}
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("scenario must declare at least one cross-domain dependency")
    for dependency in dependencies:
        if not isinstance(dependency, dict) or dependency.get("type") != "entity_transfer":
            raise ValueError("scenario dependency must be an entity_transfer object")
        if dependency.get("link_id") not in known_links:
            raise ValueError("scenario dependency references an unknown entity link")
        producer = dependency.get("producer", {})
        consumer = dependency.get("consumer", {})
        if (
            producer.get("domain_id") not in domains
            or consumer.get("domain_id") not in domains
            or producer.get("domain_id") == consumer.get("domain_id")
        ):
            raise ValueError("scenario dependency must connect two required domains")
        link = known_links[dependency["link_id"]]
        declared_endpoints = {
            (side["domain_id"], side["entity"], side["field"])
            for side in (link["left"], link["right"])
        }
        dependency_endpoints = {
            (side.get("domain_id"), side.get("entity"), side.get("field"))
            for side in (producer, consumer)
        }
        if dependency_endpoints != declared_endpoints:
            raise ValueError("scenario dependency endpoints do not match the declared entity link")
    plan = scenario.get("reference_plan")
    if not isinstance(plan, list) or len(plan) < 2:
        raise ValueError("scenario reference plan must contain at least two actions")
    plan_domains: set[str] = set()
    tool_schemas = {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in manifest["tools"]
    }
    for action in plan:
        if not isinstance(action, dict) or action.get("route") not in manifest["routes"]:
            raise ValueError("scenario plan references an unknown route")
        if not isinstance(action.get("arguments"), dict):
            raise ValueError("scenario action arguments must be an object")
        schema = tool_schemas[action["route"]]
        properties = set(schema.get("properties", {}))
        required = set(schema.get("required", []))
        supplied = set(action["arguments"])
        if not required.issubset(supplied):
            raise ValueError("scenario action is missing required tool arguments")
        if not supplied.issubset(properties):
            raise ValueError("scenario action contains undeclared tool arguments")
        plan_domains.add(manifest["routes"][action["route"]]["domain_id"])
    if len(plan_domains) < 2:
        raise ValueError("scenario plan must execute across at least two domains")
    predicates = scenario.get("predicates")
    if not isinstance(predicates, list) or not predicates:
        raise ValueError("scenario must declare executable predicates")
    for predicate in predicates:
        if not isinstance(predicate, dict) or predicate.get("kind") not in _PREDICATE_KINDS:
            raise ValueError("scenario contains an unsupported predicate")
        error = _predicate_error(manifest, predicate, tool_schemas)
        if error:
            raise ValueError(error)


def _predicate_error(
    manifest: dict[str, Any],
    predicate: dict[str, Any],
    tool_schemas: dict[str, dict[str, Any]],
) -> str | None:
    kind = predicate["kind"]
    routes = set(manifest["routes"])
    link_ids = {link["id"] for link in manifest["world"]["entity_links"]}
    if kind == "tool_called" and predicate.get("route") not in routes:
        return "tool_called predicate references an unknown route"
    if kind == "tool_order":
        if predicate.get("before") not in routes or predicate.get("after") not in routes:
            return "tool_order predicate references an unknown route"
    if kind == "result_to_argument":
        producer = predicate.get("producer")
        consumer = predicate.get("consumer")
        argument = predicate.get("consumer_argument")
        if producer not in routes or consumer not in routes:
            return "result_to_argument predicate references an unknown route"
        if argument not in tool_schemas[consumer].get("properties", {}):
            return "result_to_argument predicate references an unknown consumer argument"
        if manifest["routes"][producer]["domain_id"] == manifest["routes"][consumer]["domain_id"]:
            return "result_to_argument predicate must cross domain boundaries"
    if kind == "result_value":
        if predicate.get("route") not in routes:
            return "result_value predicate references an unknown route"
        if not _valid_path(predicate.get("path")) or "equals" not in predicate:
            return "result_value predicate requires a path and equals value"
    if (
        kind == "state_changed"
        and predicate.get("state_attribute") not in manifest["initial_state"]
    ):
        return "state_changed predicate references an unknown namespaced state attribute"
    if kind == "link_preserved" and predicate.get("link_id") not in link_ids:
        return "link_preserved predicate references an unknown entity link"
    if kind == "state_value":
        if predicate.get("state_attribute") not in manifest["initial_state"]:
            return "state_value predicate references an unknown namespaced state attribute"
        if not _valid_path(predicate.get("path")) or "equals" not in predicate:
            return "state_value predicate requires a path and equals value"
    if kind == "final_response_contains" and (
        not isinstance(predicate.get("text"), str) or not predicate["text"]
    ):
        return "final_response_contains predicate requires non-empty text"
    return None


def _valid_path(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, (str, int)) for item in value)

