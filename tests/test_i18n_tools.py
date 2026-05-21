from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

from metabolic_safety_etl.i18n.glossary import entity_translation_for, load_zh_aliases, translate_controlled, translate_structured_text
from metabolic_safety_etl.i18n.openai_client import parse_chat_completion
from metabolic_safety_etl.i18n.placeholders import protect_text, restore_text
from metabolic_safety_etl.i18n.segments import segment_text
from metabolic_safety_etl.i18n.translation_memory import TranslationMemory
from metabolic_safety_etl.i18n.validators import clean_translation_artifacts, validate_translation


class I18nToolsTest(unittest.TestCase):
    def test_controlled_glossary_translates_core_values(self) -> None:
        self.assertEqual(translate_controlled("risk_level", "Major"), "高风险")
        self.assertEqual(translate_controlled("interaction_type", "drug_interaction"), "药物相互作用")
        self.assertEqual(translate_controlled("route", "oral"), "口服")
        self.assertEqual(translate_controlled("threshold_label", "24h total reaches/exceeds 3x extracted dose candidate 0.00225 mg"), "24 小时累计达到/超过提取剂量候选值 0.00225 mg 的 3 倍")
        self.assertEqual(translate_controlled("threshold_label", "24h total reaches/exceeds 2x extracted label ceiling 0.0048 mg"), "24 小时累计达到/超过提取标签上限 0.0048 mg 的 2 倍")
        self.assertEqual(translate_controlled("threshold_label", "single dose reaches/exceeds 3x extracted dose candidate 0.03 mg"), "单次剂量达到/超过提取剂量候选值 0.03 mg 的 3 倍")
        self.assertEqual(translate_controlled("threshold_label", "single dose reaches/exceeds 1000 mg"), "单次剂量达到/超过 1000 mg")
        self.assertEqual(translate_controlled("threshold_label", "24h total reaches/exceeds 4000 mg"), "24 小时累计达到/超过 4000 mg")
        self.assertEqual(translate_controlled("threshold_label", "about 2 standard drinks"), "约 2 个标准杯")
        self.assertEqual(translate_controlled("threshold_label", "单次剂量达到/超过 1000 mg"), "单次剂量达到/超过 1000 mg")
        self.assertIsNone(translate_controlled("route", "unknown_custom_route"))

    def test_structured_ddinter_note_translation(self) -> None:
        note = "DDInter 2.0 severity=Major; raw_levels=Major; labels=Amitriptyline / Cocaine (nasal)"
        self.assertEqual(
            translate_structured_text("note", note),
            "DDInter 2.0 严重程度=高风险；原始等级=Major；标签=Amitriptyline / Cocaine (nasal)",
        )

    def test_load_zh_aliases_and_entity_translation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aliases.csv"
            path.write_text("name_en,name_zh,aliases\nWarfarin,华法林,华法林钠|Coumadin\n", encoding="utf-8")
            aliases = load_zh_aliases(path)
            translated = entity_translation_for({"id": "warfarin", "name_en": "Warfarin", "aliases": []}, aliases)
            self.assertEqual(translated["name"], "华法林")
            self.assertIn("华法林钠", translated["aliases"])
            existing = entity_translation_for({"id": "custom", "name_en": "Custom", "name_zh": "既有中文名", "aliases": ["既有别名", "EnglishAlias"]}, aliases)
            self.assertEqual(existing["status"], "imported_existing")
            self.assertEqual(existing["source"], "substance.name_zh")
            self.assertIn("既有别名", existing["aliases"])

    def test_placeholder_round_trip_and_validation(self) -> None:
        protected = protect_text("Warfarin inhibits CYP2C9 at 5 mg/day. See PMID:12345.", glossary_terms=["Warfarin"])
        self.assertIn("<PH", protected.text)
        model_output = protected.text.replace(" inhibits ", " 抑制 ").replace(" at ", " 在 ").replace(". See ", "。见 ")
        restored = restore_text(model_output, protected.placeholders)
        self.assertIn("Warfarin", restored)
        self.assertIn("CYP2C9", restored)
        self.assertIn("5 mg/day", restored)
        result = validate_translation("Warfarin inhibits CYP2C9 at 5 mg/day.", restored, protected.placeholders, model_output)
        self.assertTrue(result.ok, result.reasons)

    def test_validation_catches_missing_units(self) -> None:
        result = validate_translation("Use 5 mg/day.", "每天使用。")
        self.assertFalse(result.ok)
        self.assertTrue(any("missing" in reason for reason in result.reasons))

    def test_validation_catches_markdown(self) -> None:
        result = validate_translation("Monitor closely.", "**密切监测：**\n请复核。")
        self.assertFalse(result.ok)
        self.assertIn("unexpected_markdown", result.reasons)

    def test_validation_catches_duplicated_unit_translation(self) -> None:
        result = validate_translation("Do not exceed 10 mg daily.", "每日剂量不应超过 10 mg 毫克。")
        self.assertFalse(result.ok)
        self.assertTrue(any(reason.startswith("duplicated_unit_translation") for reason in result.reasons))

    def test_clean_translation_artifacts_removes_duplicate_units(self) -> None:
        cleaned = clean_translation_artifacts("每日剂量不应超过 10 mg 毫克；每杯含 14 g 毫升乙醇。")
        self.assertEqual(cleaned, "每日剂量不应超过 10 mg；每杯含 14 g乙醇。")
        result = validate_translation("Do not exceed 10 mg daily.", cleaned)
        self.assertTrue(result.ok, result.reasons)

    def test_translation_memory_upsert_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = TranslationMemory(Path(tmp) / "tm.sqlite")
            memory.upsert(
                locale="zh-CN",
                source_text="Monitor closely.",
                translated_text="密切监测。",
                domain="interactions",
                field_name="note",
                status="machine_unreviewed",
                validation_status="passed",
            )
            self.assertEqual(memory.usable_translation("zh-CN", "Monitor closely."), "密切监测。")
            memory.close()

    def test_segment_text_splits_long_text(self) -> None:
        segments = segment_text("A sentence. Another sentence. Final sentence.", max_chars=20)
        self.assertGreater(len(segments), 1)
        self.assertEqual(" ".join(segments), "A sentence. Another sentence. Final sentence.")

    def test_openai_response_parser(self) -> None:
        payload = {"choices": [{"message": {"content": "翻译文本"}}]}
        self.assertEqual(parse_chat_completion(payload), "翻译文本")


class I18nOverlayScriptsSmokeTest(unittest.TestCase):
    def test_extract_and_export_overlay_smoke(self) -> None:
        import importlib.util

        root = Path(__file__).resolve().parents[1]
        extract_path = root / "tools" / "i18n_extract_candidates.py"
        export_path = root / "tools" / "i18n_export_overlays.py"

        extract_spec = importlib.util.spec_from_file_location("i18n_extract_candidates", extract_path)
        extract_module = importlib.util.module_from_spec(extract_spec)
        assert extract_spec.loader is not None
        extract_spec.loader.exec_module(extract_module)

        export_spec = importlib.util.spec_from_file_location("i18n_export_overlays", export_path)
        export_module = importlib.util.module_from_spec(export_spec)
        assert export_spec.loader is not None
        export_spec.loader.exec_module(export_module)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            api = base / "api"
            interaction_path = api / "interactions" / "by-substance" / "aa" / "warfarin.json"
            interaction_path.parent.mkdir(parents=True, exist_ok=True)
            interaction_path.write_text(json.dumps([
                {
                    "interaction_id": "int1",
                    "interaction_type": "drug_interaction",
                    "risk_level": "Major",
                    "confidence": "High",
                    "source_tier": "CuratedDB",
                    "action": "monitor_closely",
                    "mechanism": "CYP2C9 inhibition may increase exposure.",
                    "note": "Monitor closely.",
                }
            ]), encoding="utf-8")
            search = api / "search" / "index.json"
            search.parent.mkdir(parents=True, exist_ok=True)
            search.write_text(json.dumps([
                {"id": "warfarin", "name_en": "Warfarin", "name_zh": None, "aliases": [], "paths": {"substance": "substances/by-id/aa/warfarin.json"}}
            ]), encoding="utf-8")
            alias_csv = base / "aliases.csv"
            alias_csv.write_text("name_en,name_zh,aliases\nWarfarin,华法林,华法林钠\n", encoding="utf-8")

            candidates, report = extract_module.extract_candidates(api, ["interactions"], "zh-CN", 1800)
            self.assertEqual(report["unique_segments"], 2)

            memory = TranslationMemory(base / "tm.sqlite")
            memory.upsert(locale="zh-CN", source_text="CYP2C9 inhibition may increase exposure.", translated_text="CYP2C9 抑制可能增加暴露量。", domain="interactions", field_name="mechanism", status="machine_unreviewed", validation_status="passed")
            memory.upsert(locale="zh-CN", source_text="Monitor closely.", translated_text="密切监测。", domain="interactions", field_name="note", status="machine_unreviewed", validation_status="passed")
            manifest = export_module.export_domain(api, api / "i18n" / "zh-CN", "interactions", memory, "zh-CN", 1800)
            entity_manifest = export_module.export_entities(api, api / "i18n" / "zh-CN", "zh-CN", alias_csv)
            memory.close()

            self.assertEqual(manifest["records"], 1)
            self.assertEqual(entity_manifest["records"], 1)
            overlay = json.loads((api / "i18n" / "zh-CN" / "interactions" / "by-substance" / "aa" / "warfarin.json").read_text(encoding="utf-8"))
            fields = overlay["items"][0]["fields"]
            self.assertEqual(fields["risk_level"], "高风险")
            self.assertEqual(fields["mechanism"], "CYP2C9 抑制可能增加暴露量。")

    def test_export_and_seed_memory_jsonl_smoke(self) -> None:
        import importlib.util

        root = Path(__file__).resolve().parents[1]
        export_path = root / "tools" / "i18n_export_memory_jsonl.py"
        seed_path = root / "tools" / "i18n_seed_memory.py"

        export_spec = importlib.util.spec_from_file_location("i18n_export_memory_jsonl", export_path)
        export_module = importlib.util.module_from_spec(export_spec)
        assert export_spec.loader is not None
        export_spec.loader.exec_module(export_module)

        seed_spec = importlib.util.spec_from_file_location("i18n_seed_memory", seed_path)
        seed_module = importlib.util.module_from_spec(seed_spec)
        assert seed_spec.loader is not None
        seed_spec.loader.exec_module(seed_module)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            memory = TranslationMemory(base / "tm.sqlite")
            memory.upsert(locale="zh-CN", source_text="Monitor closely.", translated_text="密切监测。", domain="interactions", field_name="note", status="machine_unreviewed", provider="test", validation_status="passed")
            memory.upsert(locale="zh-CN", source_text="Bad output.", translated_text="", domain="interactions", field_name="note", status="failed_validation", provider="test", validation_status="failed")
            memory.close()

            out = base / "memory.jsonl"
            count = export_module.export_memory_jsonl(base / "tm.sqlite", out, "zh-CN")
            self.assertEqual(count, 1)

            seeded = base / "seeded.sqlite"
            self.assertEqual(seed_module.seed_memory(out, seeded, "zh-CN"), 1)
            seeded_memory = TranslationMemory(seeded)
            self.assertEqual(seeded_memory.usable_translation("zh-CN", "Monitor closely."), "密切监测。")
            seeded_memory.close()


if __name__ == "__main__":
    unittest.main()
