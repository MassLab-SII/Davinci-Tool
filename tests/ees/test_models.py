import unittest

from cross_domain_scaling.models import Catalog, CatalogError


def domain(domain_id="alpha"):
    return {
        "id": domain_id,
        "name": domain_id.title(),
        "summary": "A shared record service.",
        "entities": [
            {
                "name": "record",
                "fields": ["record_id", "value"],
                "state_attribute": "records",
                "container": "mapping",
                "key_field": "record_id",
            }
        ],
        "capabilities": ["record lookup"],
        "policies": [],
        "operations": [
            {
                "name": "lookup",
                "description": "Look up a record.",
                "parameters": {
                    "type": "object",
                    "properties": {"record_id": {"type": "string"}},
                    "required": ["record_id"],
                },
            }
        ],
        "runtime": {
            "class_name": "Records",
            "source": (
                "class Records:\n"
                "    def __init__(self):\n"
                "        self.records = {'1': {'value': 'example'}}\n\n"
                "    def lookup(self, record_id):\n"
                "        return {'record_id': record_id, 'record': self.records.get(record_id)}"
            ),
        },
    }


class CatalogTests(unittest.TestCase):
    def test_catalog_round_trip(self):
        catalog = Catalog.from_data([domain("alpha"), domain("beta")])
        self.assertEqual(Catalog.from_data(catalog.to_data()), catalog)

    def test_unknown_fields_are_rejected(self):
        item = domain("alpha")
        item["typo"] = True
        with self.assertRaisesRegex(CatalogError, "unknown fields"):
            Catalog.from_data([item, domain("beta")])

    def test_required_parameter_must_exist(self):
        item = domain("alpha")
        item["operations"][0]["parameters"]["required"] = ["missing"]
        with self.assertRaisesRegex(CatalogError, "references unknown"):
            Catalog.from_data([item, domain("beta")])


if __name__ == "__main__":
    unittest.main()

