from __future__ import annotations

import inspect
import json
from typing import Any

from ..llm import JsonGenerator
from ..models import Catalog
from ..runtime import CompositeRuntime
from .links import (
    initialize_linked_state,
    state_contract_errors,
    validate_entity_links,
)
from .namespace import namespace_contract_errors


def validate_manifests(
    catalog: Catalog,
    manifests: list[dict[str, Any]],
    *,
    judge_mode: str,
    generator: JsonGenerator | None,
) -> list[dict[str, Any]]:
    if judge_mode not in {"none", "llm"}:
        raise ValueError("judge mode must be 'none' or 'llm'")
    if judge_mode == "llm" and generator is None:
        raise ValueError("LLM judge mode requires a configured generator")

    results: list[dict[str, Any]] = []
    for manifest in manifests:
        working = dict(manifest)
        checks: list[dict[str, Any]] = []
        runtime: CompositeRuntime | None = None
        try:
            runtime = CompositeRuntime(catalog, working)
            expected = set(working["routes"])
            actual = set(runtime.routes)
            if expected != actual:
                raise ValueError("runtime route table does not match manifest")
            checks.append({"name": "runtime-load", "passed": True})
        except Exception as exc:  # individual invalid domains must not abort the full build
            checks.append({"name": "runtime-load", "passed": False, "reason": str(exc)})

        namespace_errors = namespace_contract_errors(catalog, working)
        checks.append(
            {
                "name": "namespace-consistency",
                "passed": not namespace_errors,
                **({"reason": "; ".join(namespace_errors)} if namespace_errors else {}),
            }
        )

        contract_errors = (
            state_contract_errors(catalog, working, runtime) if runtime is not None else []
        )
        checks.append(
            {
                "name": "state-contract",
                "passed": runtime is not None and not contract_errors,
                **({"reason": "; ".join(contract_errors)} if contract_errors else {}),
            }
        )

        operation_errors = (
            _operation_contract_errors(catalog, working, runtime) if runtime is not None else []
        )
        checks.append(
            {
                "name": "tool-schema-contract",
                "passed": runtime is not None and not operation_errors,
                **({"reason": "; ".join(operation_errors)} if operation_errors else {}),
            }
        )

        context_ok, reason = _validate_context(catalog, working, working.get("world"))
        context_check: dict[str, Any] = {"name": "world-schema", "passed": context_ok}
        if reason:
            context_check["reason"] = reason
        checks.append(context_check)

        if runtime is not None and context_ok and not contract_errors and not operation_errors:
            try:
                evidence = initialize_linked_state(
                    catalog, runtime, working["world"]["entity_links"]
                )
                link_ok = bool(evidence) and all(item["initialized"] for item in evidence)
                initial_state = runtime.snapshot()
                json.dumps({"initial_state": initial_state, "link_evidence": evidence})
                working["initial_state"] = initial_state
                working["link_evidence"] = evidence
                checks.append(
                    {
                        "name": "linked-state-initialization",
                        "passed": link_ok,
                        **(
                            {"reason": "not every declared entity link could be initialized"}
                            if not link_ok
                            else {}
                        ),
                    }
                )
            except Exception as exc:
                checks.append(
                    {
                        "name": "linked-state-initialization",
                        "passed": False,
                        "reason": str(exc),
                    }
                )

        if judge_mode == "llm" and all(check["passed"] for check in checks):
            checks.append(_semantic_judge(working, generator))

        results.append(
            {
                **working,
                "validation": {
                    "accepted": all(check["passed"] for check in checks),
                    "checks": checks,
                },
            }
        )
    return results


def _operation_contract_errors(
    catalog: Catalog,
    manifest: dict[str, Any],
    runtime: CompositeRuntime,
) -> list[str]:
    known = catalog.by_id()
    errors: list[str] = []
    for route, binding in manifest["routes"].items():
        domain = known[binding["domain_id"]]
        operation = next(
            item for item in domain.operations if item.name == binding["operation"]
        )
        method = getattr(runtime.domain_instance(domain.id), operation.name)
        signature = inspect.signature(method)
        parameters = signature.parameters
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        accepted = {
            name
            for name, parameter in parameters.items()
            if parameter.kind
            in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
        }
        implementation_required = {
            name
            for name, parameter in parameters.items()
            if name in accepted and parameter.default is inspect.Parameter.empty
        }
        properties = set(operation.parameters.get("properties", {}))
        schema_required = set(operation.parameters.get("required", []))
        if not accepts_kwargs and not properties.issubset(accepted):
            errors.append(
                f"{route} schema declares unsupported arguments: {sorted(properties - accepted)}"
            )
        if not implementation_required.issubset(schema_required):
            errors.append(
                f"{route} schema omits required implementation arguments: "
                f"{sorted(implementation_required - schema_required)}"
            )
    return errors


def _validate_context(
    catalog: Catalog,
    manifest: dict[str, Any],
    value: Any,
) -> tuple[bool, str | None]:
    if not isinstance(value, dict):
        return False, "world must be an object"
    required = {
        "organization",
        "roles",
        "scenario",
        "shared_entities",
        "entity_links",
        "cross_domain_policies",
        "coherence_constraints",
    }
    missing = sorted(required - set(value))
    if missing:
        return False, f"world is missing fields: {', '.join(missing)}"
    if not isinstance(value["scenario"], str) or not value["scenario"].strip():
        return False, "world scenario must be a non-empty string"
    if not isinstance(value["roles"], list) or not value["roles"]:
        return False, "roles must be a non-empty array"
    link_errors = validate_entity_links(catalog, manifest, value["entity_links"])
    if link_errors:
        return False, "; ".join(link_errors)
    if not value["entity_links"]:
        return False, "a cross-domain world must declare at least one entity link"
    for field in ("shared_entities", "cross_domain_policies", "coherence_constraints"):
        if not isinstance(value[field], list):
            return False, f"{field} must be an array"
    semantic_errors = _world_semantic_errors(manifest, value)
    if semantic_errors:
        return False, "; ".join(semantic_errors)
    return True, None


def _world_semantic_errors(manifest: dict[str, Any], world: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    selected = set(manifest["domain_ids"])
    organization = world.get("organization")
    if not isinstance(organization, dict) or not organization.get("name"):
        errors.append("organization must declare a name")

    covered: set[str] = set()
    for index, role in enumerate(world["roles"]):
        if not isinstance(role, dict):
            errors.append(f"roles[{index}] must be an object")
            continue
        access = role.get("domain_access")
        if not isinstance(access, list) or not set(access).issubset(selected):
            errors.append(f"roles[{index}].domain_access references unavailable domains")
            continue
        covered.update(access)
    if covered != selected:
        errors.append("declared roles must collectively cover every composed domain")

    link_ids = {link["id"] for link in world["entity_links"]}
    for index, shared in enumerate(world["shared_entities"]):
        if not isinstance(shared, dict) or shared.get("link_id") not in link_ids:
            errors.append(f"shared_entities[{index}] references an unknown link")

    for index, policy in enumerate(world["cross_domain_policies"]):
        if not isinstance(policy, dict):
            errors.append(f"cross_domain_policies[{index}] must be an object")
            continue
        domains = policy.get("domains")
        if (
            not isinstance(domains, list)
            or len(set(domains)) < 2
            or not set(domains).issubset(selected)
        ):
            errors.append(
                f"cross_domain_policies[{index}] must reference at least two composed domains"
            )
        if not isinstance(policy.get("description"), str) or not policy["description"].strip():
            errors.append(f"cross_domain_policies[{index}] requires a description")
        predicate = policy.get("predicate")
        valid_policy_predicate = False
        if isinstance(predicate, dict) and predicate.get("kind") == "link_preserved":
            valid_policy_predicate = predicate.get("link_id") in link_ids
        if isinstance(predicate, dict) and predicate.get("kind") == "tool_order":
            before = predicate.get("before")
            after = predicate.get("after")
            valid_policy_predicate = (
                before in manifest["routes"]
                and after in manifest["routes"]
                and manifest["routes"][before]["domain_id"]
                != manifest["routes"][after]["domain_id"]
            )
        if not valid_policy_predicate:
            errors.append(
                f"cross_domain_policies[{index}] requires an executable cross-domain predicate"
            )

    for index, constraint in enumerate(world["coherence_constraints"]):
        if not isinstance(constraint, dict):
            errors.append(f"coherence_constraints[{index}] must be an object")
            continue
        if constraint.get("link_id") not in link_ids:
            errors.append(f"coherence_constraints[{index}] references an unknown link")
        if constraint.get("type") != "field_equality":
            errors.append(f"coherence_constraints[{index}] has an unsupported type")
    return errors


def _semantic_judge(
    manifest: dict[str, Any], generator: JsonGenerator | None
) -> dict[str, Any]:
    assert generator is not None
    result = generator.generate(
        system=(
            "Evaluate whether a multi-domain workspace is coherent and executable using only its "
            "declared routes. Return JSON with boolean 'passed' and string array 'reasons'."
        ),
        prompt=json.dumps(
            {
                "domain_ids": manifest["domain_ids"],
                "routes": sorted(manifest["routes"]),
                "world": manifest["world"],
            },
            ensure_ascii=False,
        ),
    )
    passed = result.get("passed") is True
    reasons = result.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    return {"name": "semantic-judge", "passed": passed, "reasons": reasons}

