import json
import sqlite3
import shutil
import tempfile
from pathlib import Path
import unittest
import zipfile
from unittest.mock import patch

from metabolic_safety_etl.raw_sources import dailymed_xml_facts, extract_half_life_hours, load_chembl_bulk_facts, load_dailymed_bulk_facts, load_foodrugs_bulk_facts, load_onsides_bulk_facts, load_openfda_bulk_facts, load_remote_raw_source_facts, write_remote_raw_source_facts_json, _chembl_pk_to_hours


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

    def test_onsides_bulk_joins_product_and_event_vocabularies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "onsides"
            source.mkdir()
            with zipfile.ZipFile(source / "onsides-v3.zip", "w") as archive:
                archive.writestr("csv/product_label.csv", "label_id,source_product_name,source_label_url\n1,Example Product,https://example.test/label\n")
                archive.writestr("csv/vocab_meddra_adverse_effect.csv", "meddra_id,meddra_name,meddra_term_type\n100,Nausea,PT\n")
                archive.writestr("csv/product_adverse_effect.csv", "product_label_id,effect_meddra_id,label_section,pred0,pred1\n1,100,AR,0.1,2.0\n")

            facts = load_onsides_bulk_facts(source)

            adverse = next(f for f in facts if f.fact_type == "adverse_event")
            self.assertEqual(adverse.subject_ids, ["example_product"])
            self.assertEqual(adverse.claim["event"], "Nausea")
            self.assertEqual(adverse.extraction_method, "bulk_csv_joined")

    def test_foodrugs_bulk_reads_mysql_dump_interactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "foodrugs"
            source.mkdir()
            (source / "FinalFooDrugs_v4.sql").write_text(
                "INSERT INTO `TM_interactions` (`TM_interactions_ID`, `texts_ID`, `start_index`, `end_index`, `food`, `drug`) VALUES "
                "(1,10,0,5,'Grapefruit','Simvastatin'),(2,11,NULL,NULL,'St. Johns Wort','Warfarin');\n",
                encoding="utf-8",
            )

            facts = load_foodrugs_bulk_facts(source)

            pairs = [f for f in facts if f.fact_type == "food_interaction"]
            self.assertEqual(len(pairs), 2)
            self.assertTrue(any(f.subject_ids == ["simvastatin", "grapefruit"] for f in pairs))
            self.assertTrue(all(f.extraction_method == "bulk_mysql_dump" for f in pairs))


class HalfLifeExtractionTests(unittest.TestCase):
    """Test half-life extraction from text and from ChEMBL activities."""

    def test_extract_half_life_hours_simple(self):
        self.assertEqual(extract_half_life_hours("The half-life is 6 hours."), 6.0)

    def test_extract_half_life_hours_range(self):
        self.assertEqual(extract_half_life_hours("The terminal half-life is 2 to 4 hours."), 3.0)

    def test_extract_half_life_hours_minutes(self):
        self.assertAlmostEqual(extract_half_life_hours("The half-life is 30 minutes."), 0.5, places=3)

    def test_extract_half_life_hours_days(self):
        self.assertAlmostEqual(extract_half_life_hours("The elimination half-life is 2 days."), 48.0, places=3)

    def test_extract_half_life_hours_t12(self):
        self.assertEqual(extract_half_life_hours("t1/2 = 12.5 hours"), 12.5)

    def test_extract_half_life_hours_none_when_absent(self):
        self.assertIsNone(extract_half_life_hours("Metabolism is primarily by CYP3A4."))

    def test_chembl_pk_to_hours_hours(self):
        self.assertEqual(_chembl_pk_to_hours(30, "hr"), 30.0)

    def test_chembl_pk_to_hours_minutes(self):
        self.assertAlmostEqual(_chembl_pk_to_hours(60, "min"), 1.0, places=3)

    def test_chembl_pk_to_hours_days(self):
        self.assertAlmostEqual(_chembl_pk_to_hours(2, "days"), 48.0, places=3)

    def test_chembl_pk_to_hours_none_for_non_numeric(self):
        self.assertIsNone(_chembl_pk_to_hours(None, "hr"))
        self.assertIsNone(_chembl_pk_to_hours("text", "hr"))

    def test_chembl_pk_to_hours_none_for_zero_or_negative(self):
        self.assertIsNone(_chembl_pk_to_hours(0, "hr"))
        self.assertIsNone(_chembl_pk_to_hours(-5, "hr"))

    def test_chembl_bulk_extracts_half_life_from_activities(self):
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
                conn.execute("CREATE TABLE assays (assay_id INTEGER PRIMARY KEY, assay_type TEXT)")
                conn.execute("CREATE TABLE compound_records (record_id INTEGER PRIMARY KEY, molregno INTEGER)")
                conn.execute("CREATE TABLE activities (activity_id INTEGER PRIMARY KEY, assay_id INTEGER, record_id INTEGER, molregno INTEGER, standard_type TEXT, standard_value REAL, standard_units TEXT, standard_relation TEXT, upper_value REAL, standard_upper_value REAL)")
                conn.execute("INSERT INTO molecule_dictionary VALUES (1, 'CHEMBL1491', 'Amlodipine', 'Small molecule')")
                conn.execute("INSERT INTO compound_properties VALUES (1, '3.0', '30', '408')")
                conn.execute("INSERT INTO assays VALUES (1, 'Binding')")
                conn.execute("INSERT INTO compound_records VALUES (100, 1)")
                conn.execute("INSERT INTO activities VALUES (1, 1, 100, 1, 'T1/2', 30, 'hr', '=', NULL, NULL)")
                conn.execute("INSERT INTO activities VALUES (2, 1, 100, 1, 'Plasma half-life', 12, 'hr', '=', NULL, NULL)")

            facts = load_chembl_bulk_facts(source)

            pk_facts = [f for f in facts if f.fact_type == "pharmacokinetics"]
            self.assertGreaterEqual(len(pk_facts), 2)
            hl_values = sorted(f.claim["half_life_hours"] for f in pk_facts)
            self.assertIn(12.0, hl_values)
            self.assertIn(30.0, hl_values)
            # Verify CuratedDB source tier
            for f in pk_facts:
                self.assertEqual(f.source_tier, "CuratedDB")
                self.assertEqual(f.confidence, "High")
                self.assertEqual(f.extraction_method, "bulk_sqlite_activities")

    def test_chembl_bulk_pk_with_upper_value(self):
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
                conn.execute("CREATE TABLE assays (assay_id INTEGER PRIMARY KEY, assay_type TEXT)")
                conn.execute("CREATE TABLE compound_records (record_id INTEGER PRIMARY KEY, molregno INTEGER)")
                conn.execute("CREATE TABLE activities (activity_id INTEGER PRIMARY KEY, assay_id INTEGER, record_id INTEGER, molregno INTEGER, standard_type TEXT, standard_value REAL, standard_units TEXT, standard_relation TEXT, upper_value REAL, standard_upper_value REAL)")
                conn.execute("INSERT INTO molecule_dictionary VALUES (1, 'CHEMBL1', 'TestDrug', 'Small molecule')")
                conn.execute("INSERT INTO compound_properties VALUES (1, '2.0', '30', '250')")
                conn.execute("INSERT INTO assays VALUES (1, 'Binding')")
                conn.execute("INSERT INTO compound_records VALUES (100, 1)")
                conn.execute("INSERT INTO activities VALUES (1, 1, 100, 1, 'Plasma half life', 8, 'hr', '=', 17, NULL)")

            facts = load_chembl_bulk_facts(source)
            pk_facts = [f for f in facts if f.fact_type == "pharmacokinetics"]
            self.assertEqual(len(pk_facts), 1)
            claim = pk_facts[0].claim
            self.assertEqual(claim["half_life_hours"], 8.0)
            self.assertEqual(claim["half_life_hours_upper"], 17.0)
            self.assertAlmostEqual(claim["half_life_hours_mean"], 12.5, places=1)

if __name__ == "__main__":
    unittest.main()
