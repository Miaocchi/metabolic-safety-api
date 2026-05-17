import json
import tempfile
from pathlib import Path
import unittest

from metabolic_safety_etl.static_api import export_static_api


class StaticApiExportTests(unittest.TestCase):
    def test_exports_search_detail_and_interaction_buckets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build"
            build.mkdir()
            (build / "manifest.json").write_text(json.dumps({"dataset_version": "test"}), encoding="utf-8")
            (build / "init_substances.json").write_text(json.dumps([
                {
                    "id": "lorazepam",
                    "name_zh": "\u52b3\u62c9\u897f\u6cee",
                    "name_en": "Lorazepam",
                    "category": "Depressant",
                    "identifiers": {"aliases": "Ativan"},
                    "cyp_tags": [],
                    "dataset_version": "test",
                },
                {
                    "id": "ethanol",
                    "name_zh": "\u4e59\u9187",
                    "name_en": "Ethanol",
                    "category": "Depressant",
                    "identifiers": {},
                    "cyp_tags": [],
                    "dataset_version": "test",
                },
            ], ensure_ascii=False), encoding="utf-8")
            (build / "init_interactions.json").write_text(json.dumps([
                {
                    "interaction_id": "int_1",
                    "substance_a_id": "ethanol",
                    "substance_b_id": "lorazepam",
                    "interaction_type": "drug_interaction",
                    "risk_level": "Major",
                    "confidence": "High",
                    "source_tier": "CuratedDB",
                    "action": "avoid_or_modify_therapy",
                    "mechanism": "CNS depression",
                    "note": "sedation",
                    "conflict_status": "consistent",
                }
            ], ensure_ascii=False), encoding="utf-8")
            (build / "init_dose_rules.json").write_text(json.dumps([
                {"rule_id": "lorazepam_single", "subject_id": "lorazepam", "thresholds": [{"limit": 10}]}
            ], ensure_ascii=False), encoding="utf-8")
            (build / "evidence_facts.json").write_text(json.dumps([
                {"fact_id": "f1", "fact_type": "substance_identity", "subject_ids": ["lorazepam"], "claim": {"name_en": "Lorazepam"}, "source_name": "Test Source", "source_tier": "CuratedDB", "confidence": "High", "risk_level": "Unknown", "review_status": "machine_checked", "use_policy": "evidence_source"}
            ], ensure_ascii=False), encoding="utf-8")

            manifest = export_static_api(build, root / "public" / "api")

            self.assertEqual(manifest["counts"]["substances"], 2)
            search = json.loads((root / "public" / "api" / "search" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual({item["id"] for item in search}, {"lorazepam", "ethanol"})
            lorazepam = next(item for item in search if item["id"] == "lorazepam")
            detail = json.loads((root / "public" / "api" / lorazepam["paths"]["substance"]).read_text(encoding="utf-8"))
            self.assertEqual(detail["name_zh"], "\u52b3\u62c9\u897f\u6cee")
            interactions = json.loads((root / "public" / "api" / lorazepam["paths"]["interactions"]).read_text(encoding="utf-8"))
            self.assertEqual(interactions[0]["substance_a_name"], "\u4e59\u9187")
            dose_rules = json.loads((root / "public" / "api" / lorazepam["paths"]["dose_rules"]).read_text(encoding="utf-8"))
            self.assertEqual(dose_rules[0]["rule_id"], "lorazepam_single")
            self.assertEqual(manifest["source_library"]["sources_count"], 1)
            self.assertTrue((root / "public" / "api" / manifest["source_library"]["index"]).exists())
            package_path = root / "public" / "api" / manifest["online_library"]["full_package"]["zip"]
            self.assertTrue(package_path.exists())
            self.assertGreater(package_path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
