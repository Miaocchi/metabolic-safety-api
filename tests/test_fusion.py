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


class HalfLifeFusionTests(unittest.TestCase):
    """Test half-life flows through fusion into substance records."""

    def test_single_pk_fact_sets_base_half_life(self):
        facts = load_facts([
            {
                "fact_type": "substance_identity",
                "subject_ids": ["test_drug"],
                "claim": {"name_en": "Test Drug", "category": "DrugLabel"},
                "source_name": "test",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["test_drug"],
                "claim": {"half_life_hours": 6.0},
                "source_tier": "Regulatory",
                "confidence": "Medium",
                "source_name": "openFDA drug label bulk",
            },
        ])
        dataset = build_dataset(facts, "test")
        substance = dataset["substances_core"][0]
        self.assertEqual(substance["base_half_life"], 6.0)

    def test_curated_db_half_life_beats_regulatory_label(self):
        """Regulatory (rank 6) + Medium should beat CuratedDB (rank 4) + High due to higher source tier."""
        facts = load_facts([
            {
                "fact_type": "substance_identity",
                "subject_ids": ["amlodipine"],
                "claim": {"name_en": "Amlodipine"},
                "source_name": "test",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["amlodipine"],
                "claim": {"half_life_hours": 25.0},
                "source_tier": "Regulatory",
                "confidence": "Medium",
                "source_name": "openFDA drug label bulk",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["amlodipine"],
                "claim": {"half_life_hours": 30.0, "standard_type": "Plasma half life"},
                "source_tier": "CuratedDB",
                "confidence": "High",
                "source_name": "ChEMBL activities",
            },
        ])
        dataset = build_dataset(facts, "test")
        substance = next(s for s in dataset["substances_core"] if s["id"] == "amlodipine")
        # Regulatory (rank 6) > CuratedDB (rank 4), so the regulatory value wins
        self.assertEqual(substance["base_half_life"], 25.0)

    def test_curated_db_half_life_beats_community(self):
        """CuratedDB (rank 4) should beat Community (rank 1) half-life."""
        facts = load_facts([
            {
                "fact_type": "substance_identity",
                "subject_ids": ["drug_z"],
                "claim": {"name_en": "Drug Z"},
                "source_name": "test",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["drug_z"],
                "claim": {"half_life_hours": 4.0},
                "source_tier": "Community",
                "confidence": "Low",
                "source_name": "PsychonautWiki GraphQL",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["drug_z"],
                "claim": {"half_life_hours": 6.0},
                "source_tier": "CuratedDB",
                "confidence": "High",
                "source_name": "ChEMBL activities",
            },
        ])
        dataset = build_dataset(facts, "test")
        substance = next(s for s in dataset["substances_core"] if s["id"] == "drug_z")
        self.assertEqual(substance["base_half_life"], 6.0)

    def test_pharmacokinetics_detail_included_in_substance(self):
        facts = load_facts([
            {
                "fact_type": "substance_identity",
                "subject_ids": ["drug_x"],
                "claim": {"name_en": "Drug X"},
                "source_name": "test",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["drug_x"],
                "claim": {"half_life_hours": 12.0},
                "source_tier": "Regulatory",
                "confidence": "Medium",
                "source_name": "openFDA drug label bulk",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["drug_x"],
                "claim": {"half_life_hours": 12.0, "standard_type": "Plasma half-life"},
                "source_tier": "CuratedDB",
                "confidence": "High",
                "source_name": "ChEMBL activities",
            },
        ])
        dataset = build_dataset(facts, "test")
        substance = next(s for s in dataset["substances_core"] if s["id"] == "drug_x")
        pk_detail = substance["pharmacokinetics_detail"]
        self.assertGreaterEqual(len(pk_detail), 2)
        # Verify Regulatory entry is first (sorted by tier descending, Regulatory=6 > CuratedDB=4)
        self.assertEqual(pk_detail[0]["source_tier"], "Regulatory")
        self.assertEqual(pk_detail[0]["half_life_hours"], 12.0)
        self.assertEqual(pk_detail[1]["source_tier"], "CuratedDB")
        self.assertEqual(pk_detail[1]["half_life_hours"], 12.0)

    def test_pk_detail_with_onset_and_duration(self):
        facts = load_facts([
            {
                "fact_type": "substance_identity",
                "subject_ids": ["drug_y"],
                "claim": {"name_en": "Drug Y"},
                "source_name": "test",
            },
            {
                "fact_type": "pharmacokinetics",
                "subject_ids": ["drug_y"],
                "claim": {"onset_minutes": 30, "duration_minutes": 360},
                "source_tier": "Community",
                "confidence": "Low",
                "source_name": "PsychonautWiki GraphQL",
            },
        ])
        dataset = build_dataset(facts, "test")
        substance = next(s for s in dataset["substances_core"] if s["id"] == "drug_y")
        self.assertEqual(substance["base_onset"], 30.0)
        self.assertEqual(substance["base_duration"], 360.0)
        self.assertEqual(len(substance["pharmacokinetics_detail"]), 1)
        self.assertEqual(substance["pharmacokinetics_detail"][0]["onset_minutes"], 30)

    def test_no_pk_fact_yields_empty_detail(self):
        facts = load_facts([
            {
                "fact_type": "substance_identity",
                "subject_ids": ["simple_drug"],
                "claim": {"name_en": "Simple Drug"},
                "source_name": "test",
            },
        ])
        dataset = build_dataset(facts, "test")
        substance = dataset["substances_core"][0]
        self.assertIsNone(substance["base_half_life"])
        self.assertEqual(substance["pharmacokinetics_detail"], [])


if __name__ == "__main__":
    unittest.main()
