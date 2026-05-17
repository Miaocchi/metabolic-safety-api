import unittest

from metabolic_safety_etl.public_enrichment import candidate_terms_from_dataset, dedupe_facts, looks_like_public_api_term
from metabolic_safety_etl.schemas import EvidenceFact


class PublicEnrichmentTests(unittest.TestCase):
    def test_candidate_terms_prefers_api_safe_english_terms(self):
        dataset = {
            "substances_core": [
                {"id": "lorazepam", "name_en": "Lorazepam", "source_summary": [{"source_tier": "CuratedDB"}]},
                {"id": "bad", "name_en": "10 mg oral tablet", "source_summary": []},
                {"id": "ibuprofen", "name_en": "Ibuprofen", "identifiers": {"aliases": "Advil|???"}, "source_summary": [{"source_tier": "Regulatory"}]},
            ]
        }

        terms = candidate_terms_from_dataset(dataset, 10)

        self.assertEqual(terms[:2], ["Ibuprofen", "Advil"] )
        self.assertIn("Lorazepam", terms)
        self.assertNotIn("10 mg oral tablet", terms)
        self.assertNotIn("???", terms)

    def test_looks_like_public_api_term_filters_label_noise(self):
        self.assertTrue(looks_like_public_api_term("Warfarin"))
        self.assertFalse(looks_like_public_api_term("500 mg oral tablet"))
        self.assertFalse(looks_like_public_api_term("???"))

    def test_dedupe_facts_keeps_one_per_fact_id(self):
        first = EvidenceFact(fact_id="same", fact_type="source_text", subject_ids=["a"], claim={"text": "old"})
        second = EvidenceFact(fact_id="same", fact_type="source_text", subject_ids=["a"], claim={"text": "new"})

        self.assertEqual(dedupe_facts([first, second])[0].claim["text"], "new")


if __name__ == "__main__":
    unittest.main()
