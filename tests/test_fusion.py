import unittest

from metabolic_safety_etl.fusion import build_dataset, load_facts
from metabolic_safety_etl.schemas import normalize_risk


class FusionTests(unittest.TestCase):
    def test_risk_aliases_are_normalized(self):
        self.assertEqual(normalize_risk("Dangerous"), "Contraindicated")
        self.assertEqual(normalize_risk("Unsafe"), "Major")
        self.assertEqual(normalize_risk("Low Risk & No Synergy"), "NoKnownClinicalSignificance")
        self.assertEqual(normalize_risk("not-a-real-risk"), "Unknown")

    def test_community_source_cannot_downgrade_more_severe_risk(self):
        facts = load_facts(
            [
                {
                    "fact_type": "drug_interaction",
                    "subject_ids": ["a", "b"],
                    "claim": {"note": "curated major"},
                    "risk_level": "Major",
                    "confidence": "Medium",
                    "source_tier": "CuratedDB",
                    "source_name": "curated",
                },
                {
                    "fact_type": "drug_interaction",
                    "subject_ids": ["a", "b"],
                    "claim": {"note": "community minor"},
                    "risk_level": "Minor",
                    "confidence": "Low",
                    "source_tier": "Community",
                    "source_name": "community",
                },
            ]
        )
        dataset = build_dataset(facts, "test")
        interaction = dataset["interactions_core"][0]
        self.assertEqual(interaction["risk_level"], "Major")
        self.assertEqual(interaction["confidence"], "Medium")
        self.assertEqual(interaction["source_tier"], "CuratedDB")
        self.assertEqual(interaction["conflict_status"], "conflicting")

    def test_unknown_is_not_treated_as_no_risk(self):
        facts = load_facts(
            [
                {
                    "fact_type": "food_interaction",
                    "subject_ids": ["a", "food"],
                    "claim": {"note": "no evidence"},
                    "risk_level": "Unknown",
                    "confidence": "Unknown",
                    "source_tier": "Community",
                    "source_name": "community",
                }
            ]
        )
        dataset = build_dataset(facts, "test")
        interaction = dataset["interactions_core"][0]
        self.assertEqual(interaction["risk_level"], "Unknown")
        self.assertEqual(interaction["action"], "show_uncertainty")


if __name__ == "__main__":
    unittest.main()
