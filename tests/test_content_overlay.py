import json
import tempfile
from pathlib import Path
import unittest

from tools.export_dose_overlay import export_content_overlay_from_sources


class ContentOverlayExportTests(unittest.TestCase):
    def test_exports_content_signal_and_pgx_detail_paths(self):
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
                    "claim": {"half_life_hours": 26, "onset_minutes": 240, "duration_minutes": 1440, "standard_type": "T1/2"},
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
                {
                    "fact_id": "ls1",
                    "fact_type": "label_section",
                    "subject_ids": ["sertraline"],
                    "claim": {"section": "warning", "text_excerpt": "Label warning excerpt"},
                    "source_name": "DailyMed",
                    "source_tier": "Regulatory",
                    "confidence": "Medium",
                },
                {
                    "fact_id": "sw1",
                    "fact_type": "safety_warning",
                    "subject_ids": ["sertraline"],
                    "claim": {"section": "warning", "warning_text": "Severe warning"},
                    "risk_level": "Major",
                    "source_name": "DailyMed",
                    "source_tier": "Regulatory",
                    "confidence": "Medium",
                },
                {
                    "fact_id": "is1",
                    "fact_type": "interaction_signal",
                    "subject_ids": ["sertraline"],
                    "claim": {"section": "interaction", "interaction_text": "Do not combine with MAOIs."},
                    "risk_level": "Major",
                    "source_name": "openFDA",
                    "source_tier": "Regulatory",
                    "confidence": "Medium",
                },
                {
                    "fact_id": "fi1",
                    "fact_type": "food_interaction",
                    "subject_ids": ["sertraline", "grapefruit"],
                    "claim": {"drug": "Sertraline", "food_or_bioactive": "Grapefruit", "note": "text-mined candidate"},
                    "source_name": "FooDrugs",
                    "source_tier": "Signal",
                    "confidence": "Low",
                },
                {
                    "fact_id": "ae1",
                    "fact_type": "adverse_event",
                    "subject_ids": ["sertraline"],
                    "claim": {"event": "Nausea", "meddra_id": "100"},
                    "source_name": "OnSIDES",
                    "source_tier": "Signal",
                    "confidence": "Low",
                },
                {
                    "fact_id": "pgx1",
                    "fact_type": "pgx_guideline",
                    "subject_ids": ["sertraline"],
                    "claim": {"guideline_id": "PA1", "genes": ["CYP2C19"], "summary": "CPIC guideline evidence"},
                    "source_name": "PharmGKB / ClinPGx guideline",
                    "source_tier": "Guideline",
                    "confidence": "High",
                },
            ]
            fact_path = root / "facts.json"
            fact_path.write_text(json.dumps(facts), encoding="utf-8")

            summary = export_content_overlay_from_sources(api, [], [fact_path], max_per_subject=4)

            self.assertEqual(summary["drug_effects"], 1)
            self.assertEqual(summary["pharmacokinetics"], 1)
            self.assertEqual(summary["enzyme_relations"], 1)
            self.assertEqual(summary["label_sections"], 1)
            self.assertEqual(summary["safety_warnings"], 1)
            self.assertEqual(summary["interaction_signals"], 1)
            self.assertEqual(summary["food_interactions"], 1)
            self.assertEqual(summary["adverse_signals"], 1)
            self.assertEqual(summary["pgx"], 1)
            search = json.loads((api / "search" / "index.json").read_text(encoding="utf-8"))
            item = next(row for row in search if row["id"] == "sertraline")
            self.assertIn("drug_effects", item["paths"])
            self.assertIn("label_sections", item["paths"])
            self.assertIn("safety_warnings", item["paths"])
            self.assertIn("interaction_signals", item["paths"])
            self.assertIn("food_interactions", item["paths"])
            self.assertIn("adverse_signals", item["paths"])
            self.assertIn("pgx", item["paths"])
            detail = json.loads((api / item["paths"]["substance"]).read_text(encoding="utf-8"))
            self.assertEqual(detail["drug_effect_count"], 1)
            self.assertEqual(detail["pharmacokinetic_count"], 1)
            self.assertEqual(detail["label_section_count"], 1)
            self.assertEqual(detail["safety_warning_count"], 1)
            self.assertEqual(detail["interaction_signal_count"], 1)
            self.assertEqual(detail["food_interaction_count"], 1)
            self.assertEqual(detail["adverse_signal_count"], 1)
            self.assertEqual(detail["pgx_count"], 1)
            effects = json.loads((api / item["paths"]["drug_effects"]).read_text(encoding="utf-8"))
            self.assertEqual(effects[0]["target"], "SLC6A4")
            pk_rows = json.loads((api / item["paths"]["pharmacokinetics"]).read_text(encoding="utf-8"))
            self.assertEqual(pk_rows[0]["half_life_hours"], 26)
            self.assertEqual(pk_rows[0]["onset_minutes"], 240)
            self.assertEqual(pk_rows[0]["duration_minutes"], 1440)
            self.assertEqual(pk_rows[0]["standard_type"], "T1/2")
            warnings = json.loads((api / item["paths"]["safety_warnings"]).read_text(encoding="utf-8"))
            self.assertEqual(warnings[0]["risk_level"], "Major")
            pgx = json.loads((api / item["paths"]["pgx"]).read_text(encoding="utf-8"))
            self.assertEqual(pgx[0]["genes"], ["CYP2C19"])
            food_item = next(row for row in search if row["id"] == "grapefruit")
            food_rows = json.loads((api / food_item["paths"]["food_interactions"]).read_text(encoding="utf-8"))
            self.assertEqual(food_rows[0]["food_or_bioactive"], "Grapefruit")
            manifest = json.loads((api / "pgx" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["records"], 1)
            self.assertTrue((api / "adverse-signals" / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
