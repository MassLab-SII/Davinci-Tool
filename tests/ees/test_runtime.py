import unittest

from test_models import domain

from cross_domain_scaling.models import Catalog
from cross_domain_scaling.runtime import CompositeRuntime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog.from_data([domain("alpha"), domain("beta")])
        self.manifest = {
            "domain_ids": ["alpha", "beta"],
            "routes": {
                "alpha__lookup": {"domain_id": "alpha", "operation": "lookup"},
                "beta__lookup": {"domain_id": "beta", "operation": "lookup"},
            },
        }

    def test_namespaced_routes_allow_same_method_name(self):
        runtime = CompositeRuntime(self.catalog, self.manifest)
        self.assertEqual(
            runtime.invoke("alpha__lookup", {"record_id": "1"})["record_id"], "1"
        )
        self.assertEqual(
            runtime.invoke("beta__lookup", {"record_id": "2"})["record_id"], "2"
        )

    def test_signature_errors_are_labeled_with_route(self):
        runtime = CompositeRuntime(self.catalog, self.manifest)
        with self.assertRaisesRegex(TypeError, "alpha__lookup"):
            runtime.invoke("alpha__lookup", {})


if __name__ == "__main__":
    unittest.main()

