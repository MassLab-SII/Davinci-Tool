import json
import unittest
from copy import deepcopy
from pathlib import Path

from cross_domain_scaling.models import Catalog
from cross_domain_scaling.pipeline import BuildOptions, build_bundle
from cross_domain_scaling.runtime import CompositeRuntime
from cross_domain_scaling.stages.verification import verify_trajectories

ROOT = Path(__file__).resolve().parents[2]


class FakeSemanticProvider:
    def embed(self, texts):
        return [[1.0, float(index + 1)] for index, _ in enumerate(texts)]

    def generate(self, *, system, prompt):
        return {
            "score": 4,
            "reason": "The contracts expose compatible identifiers and complementary operations.",
            "candidate_links": [],
        }


class FakeWorkflowProvider:
    def generate(self, *, system, prompt):
        payload = json.loads(prompt)
        if "Generate state-grounded cross-domain tasks" in system:
            link = next(
                item
                for item in payload["world"]["entity_links"]
                if {item["left"]["domain_id"], item["right"]["domain_id"]}
                == {"delivery", "notifications"}
            )
            return {
                "scenarios": [
                    {
                        "task": "Check order ORD-1 delivery and send the customer an update.",
                        "role": "cross-functional operations coordinator",
                        "required_domains": ["delivery", "notifications"],
                        "policy_ids": ["policy-001"],
                        "dependencies": [
                            {
                                "type": "entity_transfer",
                                "link_id": link["id"],
                                "producer": {
                                    "domain_id": "delivery",
                                    "entity": "delivery",
                                    "field": "order_id",
                                },
                                "consumer": {
                                    "domain_id": "notifications",
                                    "entity": "message",
                                    "field": "order_id",
                                },
                            }
                        ],
                        "reference_plan": [
                            {
                                "route": "delivery__get_delivery_by_order",
                                "arguments": {"order_id": "ORD-1"},
                            },
                            {
                                "route": "notifications__send",
                                "arguments": {
                                    "recipient": "CUS-1",
                                    "message": "Delivery is scheduled",
                                    "order_id": "ORD-1",
                                },
                            },
                        ],
                        "predicates": [
                            {
                                "kind": "tool_called",
                                "route": "delivery__get_delivery_by_order",
                            },
                            {"kind": "tool_called", "route": "notifications__send"},
                            {
                                "kind": "tool_order",
                                "before": "delivery__get_delivery_by_order",
                                "after": "notifications__send",
                            },
                            {
                                "kind": "result_to_argument",
                                "producer": "delivery__get_delivery_by_order",
                                "consumer": "notifications__send",
                                "consumer_argument": "order_id",
                            },
                            {"kind": "state_changed", "state_attribute": "notifications__messages"},
                            {"kind": "link_preserved", "link_id": link["id"]},
                        ],
                    }
                ]
            }
        history = payload["history"]
        if not history:
            return {
                "type": "tool",
                "route": "delivery__get_delivery_by_order",
                "arguments": {"order_id": "ORD-1"},
            }
        if len(history) == 1:
            return {
                "type": "tool",
                "route": "notifications__send",
                "arguments": {
                    "recipient": "CUS-1",
                    "message": "Delivery is scheduled",
                    "order_id": "ORD-1",
                },
            }
        return {"type": "final", "response": "The customer was updated."}


class FakeWorldProvider:
    def generate(self, *, system, prompt):
        payload = json.loads(prompt)
        if "Design a coherent multi-system workspace" in system:
            domains = [item["id"] for item in payload["domains"]]
            links = payload["contract_grounded_link_candidates"]
            policies = [
                {
                    "id": f"policy-{index:03d}",
                    "domains": [link["left"]["domain_id"], link["right"]["domain_id"]],
                    "description": "Preserve the linked identifier.",
                    "predicate": {"kind": "link_preserved", "link_id": link["id"]},
                }
                for index, link in enumerate(links, start=1)
            ]
            return {
                "organization": {"name": "Test Workspace", "description": "Integrated test."},
                "roles": [
                    {
                        "name": "operator",
                        "domain_access": domains,
                        "responsibilities": ["coordinate linked records"],
                    }
                ],
                "scenario": "Coordinate records across every selected domain.",
                "shared_entities": [
                    {
                        "name": f"shared-{index}",
                        "domains": [
                            link["left"]["domain_id"],
                            link["right"]["domain_id"],
                        ],
                        "link_id": link["id"],
                    }
                    for index, link in enumerate(links, start=1)
                ],
                "entity_links": links,
                "cross_domain_policies": policies,
                "coherence_constraints": [
                    {
                        "id": f"constraint-{index:03d}",
                        "link_id": link["id"],
                        "type": "field_equality",
                        "description": link["description"],
                    }
                    for index, link in enumerate(links, start=1)
                ],
            }
        return {"passed": True, "reasons": []}


EXAMPLE_CATALOG = ROOT / "environments" / "ees" / "catalog.json"


@unittest.skipUnless(EXAMPLE_CATALOG.exists(), "example EES catalog is not included in this release")
class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.from_data(json.loads(EXAMPLE_CATALOG.read_text(encoding="utf-8")))

    def test_offline_build_is_deterministic(self):
        options = BuildOptions(count=5, maximum_domains=3, seed=17)
        first = build_bundle(self.catalog, options)
        second = build_bundle(self.catalog, options)
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["generated_environments"], 5)
        self.assertEqual(first["summary"]["accepted_environments"], 5)

    def test_composed_runtime_routes_to_isolated_domain(self):
        bundle = build_bundle(
            self.catalog,
            BuildOptions(count=6, minimum_domains=2, maximum_domains=4, seed=3),
        )
        manifest = next(
            item for item in bundle["environments"] if "inventory" in item["domain_ids"]
        )
        runtime = CompositeRuntime(self.catalog, manifest)
        result = runtime.invoke("inventory__stock", {"sku": "A-1"})
        self.assertEqual(result["quantity"], 12)

    def test_bad_runtime_is_rejected_without_aborting_build(self):
        raw = self.catalog.to_data()
        raw[0]["runtime"]["class_name"] = "MissingClass"
        catalog = Catalog.from_data(raw)
        bundle = build_bundle(
            catalog,
            BuildOptions(count=4, minimum_domains=2, maximum_domains=2, seed=1),
        )
        affected = [
            item for item in bundle["environments"] if raw[0]["id"] in item["domain_ids"]
        ]
        self.assertTrue(affected)
        self.assertTrue(all(not item["validation"]["accepted"] for item in affected))

    def test_b23_manifest_namespaces_contracts_and_initializes_links(self):
        bundle = build_bundle(
            self.catalog,
            BuildOptions(count=6, minimum_domains=2, maximum_domains=3, seed=8),
        )
        manifest = next(
            item
            for item in bundle["environments"]
            if {"inventory", "orders"}.issubset(item["domain_ids"])
        )
        namespace = manifest["namespace"]
        self.assertEqual(namespace["orders"]["tools"]["get_order"], "orders__get_order")
        self.assertEqual(namespace["orders"]["entities"]["order"], "orders__order")
        self.assertEqual(namespace["orders"]["state_attributes"]["orders"], "orders__orders")
        self.assertTrue(manifest["world"]["entity_links"])
        self.assertTrue(all(item["initialized"] for item in manifest["link_evidence"]))
        self.assertTrue(all("__" in key for key in manifest["initial_state"]))

    def test_composite_runtime_restores_linked_initial_state(self):
        bundle = build_bundle(
            self.catalog,
            BuildOptions(count=6, minimum_domains=2, maximum_domains=3, seed=8),
        )
        manifest = next(
            item
            for item in bundle["environments"]
            if {"inventory", "orders"}.issubset(item["domain_ids"])
        )
        runtime = CompositeRuntime(self.catalog, manifest)
        initial = runtime.snapshot()
        runtime.invoke(
            "inventory__reserve", {"sku": "A-1", "quantity": 2, "order_id": "ORD-2"}
        )
        self.assertNotEqual(runtime.snapshot(), initial)
        runtime.reset()
        self.assertEqual(runtime.snapshot(), initial)

    def test_semantic_affinity_uses_embedding_retrieval_and_rubric(self):
        provider = FakeSemanticProvider()
        bundle = build_bundle(
            self.catalog,
            BuildOptions(
                count=3,
                maximum_domains=3,
                seed=4,
                affinity_mode="semantic",
                affinity_threshold=0.6,
            ),
            generator=provider,
            embedder=provider,
        )
        self.assertEqual(bundle["affinity_graph"]["settings"]["mode"], "semantic")
        self.assertTrue(bundle["affinity_graph"]["edges"])
        self.assertTrue(
            all(edge["rubric"] == "model" for edge in bundle["affinity_graph"]["edges"])
        )

    def test_b24_reference_rollouts_produce_executable_verification_evidence(self):
        bundle = build_bundle(
            self.catalog,
            BuildOptions(
                count=5,
                minimum_domains=2,
                maximum_domains=3,
                seed=17,
                scenarios_per_environment=1,
                scenario_mode="offline",
                rollout_mode="reference",
            ),
        )
        scenarios = [
            scenario
            for environment in bundle["environments"]
            for scenario in environment["scenarios"]
        ]
        self.assertEqual(len(scenarios), 5)
        self.assertTrue(all(scenario["verification"]["accepted"] for scenario in scenarios))
        self.assertTrue(
            all(
                len({event["domain_id"] for event in scenario["trajectory"]["events"]}) >= 2
                for scenario in scenarios
            )
        )
        self.assertTrue(
            all(
                scenario["verification"]["outcome_evidence"]["initial_state"]
                != scenario["verification"]["outcome_evidence"]["final_state"]
                for scenario in scenarios
            )
        )

    def test_b24_rejects_a_trajectory_without_observed_value_transfer(self):
        bundle = build_bundle(
            self.catalog,
            BuildOptions(
                count=1,
                minimum_domains=3,
                maximum_domains=3,
                seed=17,
                scenarios_per_environment=1,
                rollout_mode="reference",
            ),
        )
        environments = deepcopy(bundle["environments"])
        scenario = environments[0]["scenarios"][0]
        scenario["trajectory"]["events"][1]["arguments"]["order_id"] = "UNOBSERVED"
        checked = verify_trajectories(self.catalog, environments)
        self.assertFalse(checked[0]["scenarios"][0]["verification"]["accepted"])

    def test_b24_model_task_and_rollout_use_only_visible_contract(self):
        provider = FakeWorkflowProvider()
        bundle = build_bundle(
            self.catalog,
            BuildOptions(
                count=1,
                minimum_domains=3,
                maximum_domains=3,
                seed=17,
                scenarios_per_environment=1,
                scenario_mode="llm",
                rollout_mode="llm",
            ),
            generator=provider,
        )
        scenario = bundle["environments"][0]["scenarios"][0]
        self.assertTrue(scenario["verification"]["accepted"])
        self.assertEqual(len(scenario["trajectory"]["events"]), 2)

    def test_model_generated_world_is_contract_checked_and_judged(self):
        bundle = build_bundle(
            self.catalog,
            BuildOptions(
                count=1,
                minimum_domains=3,
                maximum_domains=3,
                seed=17,
                context_mode="llm",
                judge_mode="llm",
            ),
            generator=FakeWorldProvider(),
        )
        environment = bundle["environments"][0]
        self.assertTrue(environment["validation"]["accepted"])
        self.assertEqual(
            environment["validation"]["checks"][-1]["name"], "semantic-judge"
        )


if __name__ == "__main__":
    unittest.main()

