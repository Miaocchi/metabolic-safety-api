import json
import shutil
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

from metabolic_safety_etl.raw_sources import dailymed_xml_facts, load_openfda_bulk_facts, load_remote_raw_source_facts


class RawSourceAdapterTests(unittest.TestCase):
    def test_openfda_bulk_extracts_identity_pk_and_cyp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "openfda_label"
            source.mkdir()
            payload = {
                "results": [
                    {
                        "set_id": "set-1",
                        "openfda": {
                            "generic_name": ["Example Drug"],
                            "brand_name": ["ExampleBrand"],
                            "rxcui": ["123"],
                        },
                        "pharmacokinetics": ["The terminal half-life is 2 to 4 hours. Metabolism is primarily by CYP3A4."],
                    }
                ]
            }
            with zipfile.ZipFile(source / "labels.zip", "w") as archive:
                archive.writestr("drug-label-0001.json", json.dumps(payload))

            facts = load_openfda_bulk_facts(source)

            self.assertTrue(any(f.fact_type == "substance_identity" for f in facts))
            pk = next(f for f in facts if f.fact_type == "pharmacokinetics")
            self.assertEqual(pk.claim["half_life_hours"], 3.0)
            self.assertTrue(any(f.fact_type == "enzyme_relation" and f.claim["tag"] == "CYP3A4_substrate" for f in facts))

    def test_dailymed_xml_extracts_identity_pk_and_cyp(self):
        xml = b'''
        <document xmlns="urn:hl7-org:v3">
          <setId root="abc"/>
          <title>Example DailyMed Drug</title>
          <component><structuredBody><component><section>
            <title>CLINICAL PHARMACOLOGY</title>
            <text>The half-life is 30 minutes. It is an inhibitor of CYP2D6.</text>
          </section></component></structuredBody></component>
        </document>
        '''

        facts = dailymed_xml_facts(xml)

        self.assertTrue(any(f.fact_type == "substance_identity" for f in facts))
        pk = next(f for f in facts if f.fact_type == "pharmacokinetics")
        self.assertEqual(pk.claim["half_life_hours"], 0.5)
        self.assertTrue(any(f.fact_type == "enzyme_relation" and f.claim["tag"] == "CYP2D6_inhibitor" for f in facts))



    def test_remote_stream_downloads_one_part_then_extracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_zip = root / "remote-openfda.zip"
            payload = {
                "results": [
                    {
                        "set_id": "remote-1",
                        "openfda": {"generic_name": ["Remote Drug"]},
                        "pharmacokinetics": ["The half-life is 6 hours."],
                    }
                ]
            }
            with zipfile.ZipFile(source_zip, "w") as archive:
                archive.writestr("drug-label-0001.json", json.dumps(payload))

            def fake_manifest(key):
                self.assertEqual(key, "openfda_label")
                return {"parts": [{"name": "remote.zip", "url": "https://example.test/remote.zip"}], "source_url": "test"}

            def fake_download(url, target):
                self.assertEqual(url, "https://example.test/remote.zip")
                shutil.copyfile(source_zip, target)

            with patch("metabolic_safety_etl.raw_sources.fetch_remote_bulk_manifest", fake_manifest), patch("metabolic_safety_etl.raw_sources.download_url", fake_download):
                facts, summary = load_remote_raw_source_facts(["openfda_label"], temp_dir=root / "stream", max_records_per_source=10)

            self.assertEqual(summary["openfda_label"]["downloaded_parts"], 1)
            self.assertTrue(any(f.fact_type == "substance_identity" for f in facts))
            self.assertTrue(any(f.fact_type == "pharmacokinetics" and f.claim["half_life_hours"] == 6.0 for f in facts))

if __name__ == "__main__":
    unittest.main()