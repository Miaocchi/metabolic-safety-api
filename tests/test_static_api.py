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

    def test_keeps_low_count_adverse_signals_minor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build"
            build.mkdir()
            (build / "manifest.json").write_text(json.dumps({"dataset_version": "test"}), encoding="utf-8")
            (build / "init_substances.json").write_text(json.dumps([
                {"id": "donepezil", "name_zh": "多奈哌齐", "name_en": "Donepezil", "identifiers": {}, "cyp_tags": []}
            ], ensure_ascii=False), encoding="utf-8")
            (build / "init_interactions.json").write_text("[]", encoding="utf-8")
            (build / "init_dose_rules.json").write_text("[]", encoding="utf-8")
            (build / "evidence_facts.json").write_text(json.dumps([
                {
                    "fact_id": "sig_low",
                    "fact_type": "adverse_event_signal",
                    "subject_ids": ["donepezil"],
                    "claim": {"reaction": "ECG QT prolonged", "reaction_label_zh": "常见共报告事件", "count": 6},
                    "source_name": "openFDA FAERS adverse event",
                    "source_tier": "Signal",
                    "confidence": "Low",
                    "risk_level": "Moderate",
                }
            ], ensure_ascii=False), encoding="utf-8")

            export_static_api(build, root / "public" / "api")

            signal = json.loads((root / "public" / "api" / "adverse_signals" / "donepezil.json").read_text(encoding="utf-8"))
            self.assertEqual(signal["risk_level"], "Minor")


class StaticApiHalfLifeTests(unittest.TestCase):
    """Test half-life and pharmacokinetics detail in static API output."""

    def _build_substance_with_pk(self, tmp: str, substance: dict, pk_detail: list | None = None):
        root = Path(tmp)
        build = root / "build"
        build.mkdir()
        substance_record = {
            "id": substance.get("id", "test_drug"),
            "name_en": substance.get("name_en", "Test Drug"),
            "identifiers": {},
            "cyp_tags": [],
            "dataset_version": "test",
            "base_half_life": substance.get("base_half_life"),
            **{k: v for k, v in substance.items() if k not in ("id", "name_en", "base_half_life")},
        }
        if pk_detail is not None:
            substance_record["pharmacokinetics_detail"] = pk_detail
        (build / "manifest.json").write_text(json.dumps({"dataset_version": "test"}), encoding="utf-8")
        (build / "init_substances.json").write_text(json.dumps([substance_record], ensure_ascii=False), encoding="utf-8")
        (build / "init_interactions.json").write_text("[]", encoding="utf-8")
        (build / "init_dose_rules.json").write_text("[]", encoding="utf-8")
        (build / "evidence_facts.json").write_text("[]", encoding="utf-8")
        return root, build

    def test_substance_detail_includes_base_half_life(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, build = self._build_substance_with_pk(tmp, {"id": "amlodipine", "name_en": "Amlodipine", "base_half_life": 30.0})
            export_static_api(build, root / "api")
            search = json.loads((root / "api" / "search" / "index.json").read_text(encoding="utf-8"))
            substance_path = search[0]["paths"]["substance"]
            detail = json.loads((root / "api" / substance_path).read_text(encoding="utf-8"))
            self.assertEqual(detail["base_half_life"], 30.0)

    def test_substance_detail_includes_pharmacokinetics_array(self):
        pk_detail = [
            {
                "half_life_hours": 30.0,
                "source_name": "ChEMBL activities",
                "source_tier": "CuratedDB",
                "confidence": "High",
            },
            {
                "half_life_hours": 25.0,
                "source_name": "openFDA drug label bulk",
                "source_tier": "Regulatory",
                "confidence": "Medium",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root, build = self._build_substance_with_pk(tmp, {"id": "amlodipine", "name_en": "Amlodipine", "base_half_life": 30.0}, pk_detail)
            export_static_api(build, root / "api")
            search = json.loads((root / "api" / "search" / "index.json").read_text(encoding="utf-8"))
            substance_path = search[0]["paths"]["substance"]
            detail = json.loads((root / "api" / substance_path).read_text(encoding="utf-8"))
            self.assertIn("pharmacokinetics", detail)
            self.assertEqual(len(detail["pharmacokinetics"]), 2)
            # CuratedDB entry is first
            self.assertEqual(detail["pharmacokinetics"][0]["source_tier"], "CuratedDB")
            self.assertEqual(detail["pharmacokinetics"][0]["half_life_hours"], 30.0)
            self.assertEqual(detail["pharmacokinetics"][1]["source_tier"], "Regulatory")
            self.assertEqual(detail["pharmacokinetics"][1]["half_life_hours"], 25.0)

    def test_substance_without_pk_detail_omits_pharmacokinetics(self):
        """When no PK detail exists, the key should be omitted from compact output."""
        with tempfile.TemporaryDirectory() as tmp:
            root, build = self._build_substance_with_pk(tmp, {"id": "simple", "name_en": "Simple"})
            export_static_api(build, root / "api")
            search = json.loads((root / "api" / "search" / "index.json").read_text(encoding="utf-8"))
            substance_path = search[0]["paths"]["substance"]
            detail = json.loads((root / "api" / substance_path).read_text(encoding="utf-8"))
            self.assertNotIn("pharmacokinetics", detail)

    def test_substance_detail_pk_with_extended_fields(self):
        """Verify clearance, volume_distribution, bioavailability pass through."""
        pk_detail = [
            {
                "half_life_hours": 12.0,
                "source_name": "openFDA drug label bulk",
                "source_tier": "Regulatory",
                "confidence": "Medium",
                "bioavailability": 0.85,
                "clearance": "10 L/hr",
                "volume_distribution": "200 L",
                "route": "oral",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root, build = self._build_substance_with_pk(tmp, {"id": "test_drug", "name_en": "Test Drug", "base_half_life": 12.0}, pk_detail)
            export_static_api(build, root / "api")
            search = json.loads((root / "api" / "search" / "index.json").read_text(encoding="utf-8"))
            substance_path = search[0]["paths"]["substance"]
            detail = json.loads((root / "api" / substance_path).read_text(encoding="utf-8"))
            pk = detail["pharmacokinetics"][0]
            self.assertEqual(pk["bioavailability"], 0.85)
            self.assertEqual(pk["clearance"], "10 L/hr")
            self.assertEqual(pk["route"], "oral")


if __name__ == "__main__":
    unittest.main()
