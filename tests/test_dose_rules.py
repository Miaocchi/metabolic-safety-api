import unittest

from metabolic_safety_etl.fusion import build_dataset, load_facts
from metabolic_safety_etl.dose_rules import extract_dose_candidate_facts


class DoseRuleNormalizationTests(unittest.TestCase):
    def test_source_text_promotes_explicit_maximum_daily_rule(self):
        facts = load_facts([
            {
                "fact_type": "source_text",
                "subject_ids": ["Example Hydrochloride Oral Tablet"],
                "claim": {
                    "section": "dosage_and_administration",
                    "text": "The maximum recommended dosage is 20 mg per day. Maximum single dose is 5 mg.",
                },
                "source_tier": "Regulatory",
                "source_name": "Test Label",
                "confidence": "High",
            }
        ])

        dataset = build_dataset(facts, "test")

        self.assertEqual(len(dataset["dose_rules_core"]), 1)
        rule = dataset["dose_rules_core"][0]
        self.assertEqual(rule["schema_version"], "dose_rule_v2")
        self.assertEqual(rule["subject_id"], "example")
        self.assertEqual(rule["unit"], "mg")
        self.assertEqual(rule["basis"], "adult_or_unspecified_label_ceiling")
        self.assertIn({"kind": "window", "level": "Moderate", "limit": 20.0, "label": "24h total reaches/exceeds extracted label ceiling 20 mg"}, rule["thresholds"])
        self.assertIn({"kind": "single", "level": "Moderate", "limit": 5.0, "label": "single dose reaches/exceeds extracted label ceiling 5 mg"}, rule["thresholds"])

    def test_routine_dose_mentions_are_not_promoted_without_maximum_language(self):
        facts = extract_dose_candidate_facts(
            "example_drug",
            "The recommended starting dosage is 5 mg twice daily and may be titrated.",
            "Test Label",
            "https://example.test",
            "test",
        )

        dataset = build_dataset(facts, "test")

        self.assertEqual(dataset["dose_rules_core"], [])

    def test_existing_curated_rule_blocks_auto_rule_for_same_normalized_subject(self):
        facts = load_facts([
            {
                "fact_type": "dose_rule",
                "subject_ids": ["example"],
                "claim": {
                    "rule_id": "curated_example",
                    "unit": "mg",
                    "window_hours": 24,
                    "thresholds": [{"kind": "window", "level": "Major", "limit": 10}],
                },
                "source_name": "Curated",
                "source_tier": "Regulatory",
                "confidence": "High",
            },
            {
                "fact_type": "source_text",
                "subject_ids": ["Example Hydrochloride Tablet"],
                "claim": {"section": "dosage_and_administration", "text": "Maximum dose is 20 mg per day."},
                "source_name": "Label",
                "source_tier": "Regulatory",
                "confidence": "High",
            },
        ])

        dataset = build_dataset(facts, "test")

        self.assertEqual([rule["rule_id"] for rule in dataset["dose_rules_core"]], ["curated_example"])


if __name__ == "__main__":
    unittest.main()
