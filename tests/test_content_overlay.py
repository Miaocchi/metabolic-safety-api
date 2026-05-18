import json
import tempfile
from pathlib import Path
import unittest

from tools.export_dose_overlay import export_content_overlay_from_sources


class ContentOverlayExportTests(unittest.TestCase):
    def test_exports_drug_effect_pk_and_enzyme_detail_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = root / "public" / "api"
            (api / "search").mkdir(parents=True)
            (api / "search" / "index.json").write_text("[]", encoding="utf-8")
            (api / "manifest.json").write_text(json.dumps({"counts": {}}), encoding="utf-8")
            facts = [
                {
                    "fact_id": "id1",
                    "fact_type": "substance_identity",
                    "subject_ids": ["sertraline"],
                    "claim": {"name_en": "Sertraline", "name_zh": "\u820d\u66f2\u6797", "aliases": ["Zoloft"]},
                    "source_name": "identity",
                    "source_tier": "Regulatory",
                    "confidence": "High",
                },
                {
                    "fact_id": "fx1",
                    "fact_type": "drug_effect",
                    "subject_ids": ["sertraline"],
                    "claim": {"mechanism_of_action": "selective serotonin reuptake inhibition", "target": "SLC6A4", "action_type": "INHIBITOR"},
                    "source_name": "ChEMBL drug mechanism",
                    "source_tier": "CuratedDB",
                    "confidence": "High",
                    "evidence_quote": "ChEMBL mechanism",
                },
                {
                    "fact_id": "pk1",
                    "fact_type": "pharmacokinetics",
                    "subject_ids": ["sertraline"],
                    "claim": {"half_life_hours": 26},
                    "source_name": "DailyMed",
                    "source_tier": "Regulatory",
                    "confidence": "Medium",
                },
                {
                    "fact_id": "ez1",
                    "fact_type": "enzyme_relation",
                    "subject_ids": ["sertraline"],
                    "claim": {"tag": "CYP2D6_inhibitor", "enzyme": "CYP2D6", "relation": "inhibitor"},
                    "source_name": "openFDA",
                    "source_tier": "Regulatory",
                    "confidence": "Medium",
                },
            ]
            fact_path = root / "facts.json"
            fact_path.write_text(json.dumps(facts), encoding="utf-8")

            summary = export_content_overlay_from_sources(api, [], [fact_path], max_per_subject=4)

            self.assertEqual(summary["drug_effects"], 1)
            self.assertEqual(summary["pharmacokinetics"], 1)
            self.assertEqual(summary["enzyme_relations"], 1)
            search = json.loads((api / "search" / "index.json").read_text(encoding="utf-8"))
            item = search[0]
            self.assertIn("drug_effects", item["paths"])
            detail = json.loads((api / item["paths"]["substance"]).read_text(encoding="utf-8"))
            self.assertEqual(detail["drug_effect_count"], 1)
            self.assertEqual(detail["pharmacokinetic_count"], 1)
            effects = json.loads((api / item["paths"]["drug_effects"]).read_text(encoding="utf-8"))
            self.assertEqual(effects[0]["target"], "SLC6A4")


if __name__ == "__main__":
    unittest.main()
