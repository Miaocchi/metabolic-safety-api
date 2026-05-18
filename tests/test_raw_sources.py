import json
import sqlite3
import shutil
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

from metabolic_safety_etl.raw_sources import dailymed_xml_facts, load_chembl_bulk_facts, load_dailymed_bulk_facts, load_openfda_bulk_facts, load_remote_raw_source_facts, write_remote_raw_source_facts_json


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
                        "indications_and_usage": ["Example Drug is indicated for attention symptoms."],
                        "mechanism_of_action": ["Example Drug blocks norepinephrine transporters."],
                        "dosage_and_administration": ["The maximum recommended dosage is 20 mg per day."],
                        "overdosage": ["OVERDOSAGE may cause coma and respiratory depression."],
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
            self.assertTrue(any(f.fact_type == "drug_effect" and "norepinephrine" in str(f.claim) for f in facts))
            self.assertTrue(any(f.fact_type == "dose_candidate" and f.claim["candidate_kind"] == "max_daily_candidate" for f in facts))
            self.assertTrue(any(f.fact_type == "overdose_warning" for f in facts))

    def test_dailymed_xml_extracts_identity_pk_and_cyp(self):
        xml = b'''
        <document xmlns="urn:hl7-org:v3">
          <setId root="abc"/>
          <title>Example DailyMed Drug</title>
          <component><structuredBody><component><section>
            <title>CLINICAL PHARMACOLOGY</title>
            <text>The half-life is 30 minutes. It is an inhibitor of CYP2D6.</text>
          </section></component><component><section>
            <title>MECHANISM OF ACTION</title>
            <text>Example DailyMed Drug antagonizes a receptor.</text>
          </section></component></structuredBody></component>
        </document>
        '''

        facts = dailymed_xml_facts(xml)

        self.assertTrue(any(f.fact_type == "substance_identity" for f in facts))
        pk = next(f for f in facts if f.fact_type == "pharmacokinetics")
        self.assertEqual(pk.claim["half_life_hours"], 0.5)
        self.assertTrue(any(f.fact_type == "enzyme_relation" and f.claim["tag"] == "CYP2D6_inhibitor" for f in facts))
        self.assertTrue(any(f.fact_type == "drug_effect" and "antagonizes" in str(f.claim) for f in facts))


    def test_dailymed_bulk_reads_nested_zip_xml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "dailymed_spl"
            source.mkdir()
            xml = b'''
            <document xmlns="urn:hl7-org:v3">
              <setId root="nested"/>
              <title>Nested DailyMed Drug</title>
              <component><structuredBody><component><section>
                <title>DOSAGE AND ADMINISTRATION</title>
                <text>The maximum recommended dosage is 50 mg per day.</text>
              </section></component><component><section>
                <title>OVERDOSAGE</title>
                <text>OVERDOSAGE may cause hypotension and severe sedation.</text>
              </section></component></structuredBody></component>
            </document>
            '''
            inner_bytes = root / "inner.zip"
            with zipfile.ZipFile(inner_bytes, "w") as inner:
                inner.writestr("label.xml", xml)
            with zipfile.ZipFile(source / "outer.zip", "w") as outer:
                outer.write(inner_bytes, "nested/inner.zip")

            facts = load_dailymed_bulk_facts(source)

            self.assertTrue(any(f.fact_type == "substance_identity" for f in facts))
            self.assertTrue(any(f.fact_type == "dose_candidate" for f in facts))
            self.assertTrue(any(f.fact_type == "overdose_warning" for f in facts))




    def test_chembl_bulk_extracts_drug_mechanism(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp)
            source = root / "chembl"
            source.mkdir()
            db_path = source / "chembl.sqlite"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE molecule_dictionary (molregno INTEGER, chembl_id TEXT, pref_name TEXT, molecule_type TEXT)")
                conn.execute("CREATE TABLE compound_properties (molregno INTEGER, alogp TEXT, psa TEXT, full_mwt TEXT)")
                conn.execute("CREATE TABLE drug_mechanism (molregno INTEGER, tid INTEGER, mechanism_of_action TEXT, action_type TEXT)")
                conn.execute("CREATE TABLE target_dictionary (tid INTEGER, pref_name TEXT)")
                conn.execute("INSERT INTO molecule_dictionary VALUES (1, 'CHEMBL1', 'Atomoxetine', 'Small molecule')")
                conn.execute("INSERT INTO compound_properties VALUES (1, '2.4', '30', '255')")
                conn.execute("INSERT INTO target_dictionary VALUES (10, 'Norepinephrine transporter')")
                conn.execute("INSERT INTO drug_mechanism VALUES (1, 10, 'Norepinephrine uptake inhibition', 'INHIBITOR')")

            facts = load_chembl_bulk_facts(source)

            self.assertTrue(any(f.fact_type == "substance_identity" for f in facts))
            effect = next(f for f in facts if f.fact_type == "drug_effect")
            self.assertEqual(effect.claim["target"], "Norepinephrine transporter")
            self.assertEqual(effect.claim["action_type"], "INHIBITOR")

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


    def test_remote_stream_writer_outputs_valid_json_without_accumulating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_zip = root / "remote-openfda.zip"
            payload = {
                "results": [
                    {
                        "set_id": "remote-writer-1",
                        "openfda": {"generic_name": ["Remote Writer Drug"]},
                        "mechanism_of_action": ["Remote Writer Drug inhibits a transporter."],
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

            out_path = root / "facts.json"
            summary_path = root / "summary.json"
            with patch("metabolic_safety_etl.raw_sources.fetch_remote_bulk_manifest", fake_manifest), patch("metabolic_safety_etl.raw_sources.download_url", fake_download):
                summary = write_remote_raw_source_facts_json(["openfda_label"], out_path, summary_out=summary_path, temp_dir=root / "stream")

            rows = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["openfda_label"]["downloaded_parts"], 1)
            self.assertTrue(any(row["fact_type"] == "drug_effect" for row in rows))
            self.assertEqual(json.loads(summary_path.read_text(encoding="utf-8"))["openfda_label"]["facts"], len(rows))

if __name__ == "__main__":
    unittest.main()