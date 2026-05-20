"""Unit tests for desktop_app.services.security – URL/path policy helpers."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure the repo root is importable (desktop_app is a top-level package).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop_app.services.security import (
    _int_param,
    active_seed_db,
    clean_faers_query_term,
    looks_like_public_api_term,
    safe_filename,
    split_candidate_terms,
    stable_text_hash,
    validate_download_url,
    validate_path_within_base,
)


class IntParamTests(unittest.TestCase):
    def test_returns_int_value(self):
        self.assertEqual(_int_param({"limit": ["42"]}, "limit", 10), 42)

    def test_returns_default_when_key_missing(self):
        self.assertEqual(_int_param({}, "limit", 10), 10)

    def test_returns_default_when_value_not_int(self):
        self.assertEqual(_int_param({"limit": ["abc"]}, "limit", 10), 10)

    def test_returns_default_on_empty_list(self):
        # Empty list should return default gracefully, not raise.
        self.assertEqual(_int_param({"limit": []}, "limit", 10), 10)

    def test_handles_negative_values(self):
        self.assertEqual(_int_param({"offset": ["-5"]}, "offset", 0), -5)


class SafeFilenameTests(unittest.TestCase):
    def test_strips_url_path(self):
        self.assertEqual(safe_filename("https://example.com/data/file.tar.gz"), "file.tar.gz")

    def test_sanitises_unsafe_chars(self):
        result = safe_filename("file name@#$%.txt")
        self.assertNotIn("@", result)
        self.assertNotIn("#", result)
        self.assertNotIn("%", result)
        self.assertTrue(result.endswith(".txt"))

    def test_returns_fallback_for_empty(self):
        self.assertEqual(safe_filename(""), "download.bin")

    def test_sanitises_only_unsafe_chars(self):
        # After substitution the string becomes "_", which is non-empty,
        # so no fallback is needed.
        self.assertEqual(safe_filename("@#$"), "_")

    def test_preserves_dots_and_parens(self):
        result = safe_filename("chembl_35_sqlite.tar.gz")
        self.assertEqual(result, "chembl_35_sqlite.tar.gz")

    def test_handles_path_without_slash(self):
        result = safe_filename("simple_file.txt")
        self.assertEqual(result, "simple_file.txt")


class ActiveSeedDbTests(unittest.TestCase):
    def test_returns_default_when_no_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            import desktop_app.services.security as sec
            old_build = sec.BUILD
            old_seed = sec.SEED_DB
            old_ptr = sec.ACTIVE_DB_POINTER
            try:
                build = Path(tmp)
                sec.BUILD = build
                sec.SEED_DB = build / "app_seed.sqlite"
                sec.ACTIVE_DB_POINTER = build / "active_seed_db.txt"
                self.assertEqual(active_seed_db(), build / "app_seed.sqlite")
            finally:
                sec.BUILD = old_build
                sec.SEED_DB = old_seed
                sec.ACTIVE_DB_POINTER = old_ptr

    def test_follows_pointer_when_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            import desktop_app.services.security as sec
            build = Path(tmp)
            old_build = sec.BUILD
            old_seed = sec.SEED_DB
            old_ptr = sec.ACTIVE_DB_POINTER
            try:
                sec.BUILD = build
                sec.SEED_DB = build / "app_seed.sqlite"
                sec.ACTIVE_DB_POINTER = build / "active_seed_db.txt"
                named_db = build / "app_seed.test.100.123.sqlite"
                named_db.write_text("fake", encoding="utf-8")
                sec.ACTIVE_DB_POINTER.write_text(named_db.name, encoding="utf-8")
                self.assertEqual(active_seed_db(), named_db)
            finally:
                sec.BUILD = old_build
                sec.SEED_DB = old_seed
                sec.ACTIVE_DB_POINTER = old_ptr

    def test_rejects_pointer_escaping_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            import desktop_app.services.security as sec
            build = Path(tmp) / "build"
            build.mkdir()
            old_build = sec.BUILD
            old_seed = sec.SEED_DB
            old_ptr = sec.ACTIVE_DB_POINTER
            try:
                sec.BUILD = build
                sec.SEED_DB = build / "app_seed.sqlite"
                sec.ACTIVE_DB_POINTER = build / "active_seed_db.txt"
                # Write a pointer that tries to escape build/
                sec.ACTIVE_DB_POINTER.write_text("../evil.sqlite", encoding="utf-8")
                # Should fall back to default
                self.assertEqual(active_seed_db(), build / "app_seed.sqlite")
            finally:
                sec.BUILD = old_build
                sec.SEED_DB = old_seed
                sec.ACTIVE_DB_POINTER = old_ptr


class ValidatePathWithinBaseTests(unittest.TestCase):
    def test_accepts_path_within_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            base.mkdir()
            target = base / "sub" / "file.txt"
            target.parent.mkdir(parents=True)
            target.write_text("ok", encoding="utf-8")
            result = validate_path_within_base(target, base)
            self.assertEqual(result, target.resolve())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            base.mkdir()
            evil = base / ".." / "etc" / "passwd"
            with self.assertRaises(ValueError):
                validate_path_within_base(evil, base)

    def test_rejects_absolute_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "base"
            base.mkdir()
            with self.assertRaises(ValueError):
                validate_path_within_base(Path("/etc/passwd"), base)


class LooksLikePublicApiTermTests(unittest.TestCase):
    def test_accepts_normal_drug_name(self):
        self.assertTrue(looks_like_public_api_term("Ibuprofen"))

    def test_rejects_empty(self):
        self.assertFalse(looks_like_public_api_term(""))

    def test_rejects_pure_digits(self):
        self.assertFalse(looks_like_public_api_term("12345"))

    def test_rejects_single_char(self):
        self.assertFalse(looks_like_public_api_term("A"))

    def test_rejects_noisy_form(self):
        self.assertFalse(looks_like_public_api_term("Ibuprofen oral tablet"))

    def test_rejects_curly_braces(self):
        self.assertFalse(looks_like_public_api_term("drug{name}"))

    def test_rejects_starts_with_digit(self):
        self.assertFalse(looks_like_public_api_term("3M drug"))

    def test_accepts_hyphenated(self):
        self.assertTrue(looks_like_public_api_term("L-amphetamine"))

    def test_rejects_too_many_spaces(self):
        self.assertFalse(looks_like_public_api_term("a b c d e f g"))


class CleanFaersQueryTermTests(unittest.TestCase):
    def test_clean_simple_name(self):
        self.assertEqual(clean_faers_query_term("Ibuprofen"), "Ibuprofen")

    def test_strips_dosage(self):
        result = clean_faers_query_term("IBUPROFEN 200MG ORAL TABLET")
        self.assertNotIn("200", result)
        self.assertNotIn("ORAL", result)

    def test_rejects_with_digits(self):
        self.assertEqual(clean_faers_query_term("Drug123"), "")

    def test_rejects_empty(self):
        self.assertEqual(clean_faers_query_term(""), "")

    def test_rejects_none(self):
        self.assertEqual(clean_faers_query_term(None), "")

    def test_strips_brackets(self):
        result = clean_faers_query_term("[INN] Aspirin")
        self.assertEqual(result, "Aspirin")

    def test_rejects_too_short(self):
        self.assertEqual(clean_faers_query_term("AB"), "")

    def test_rejects_slashes(self):
        self.assertEqual(clean_faers_query_term("Drug/A"), "")


class SplitCandidateTermsTests(unittest.TestCase):
    def test_single_value(self):
        self.assertEqual(split_candidate_terms("Aspirin"), ["Aspirin"])

    def test_slash_separated(self):
        result = split_candidate_terms("Aspirin / ASA")
        self.assertEqual(result, ["Aspirin / ASA", "Aspirin", "ASA"])

    def test_pipe_separated(self):
        result = split_candidate_terms("Aspirin|ASA")
        self.assertEqual(result, ["Aspirin|ASA", "Aspirin", "ASA"])

    def test_none_value(self):
        self.assertEqual(split_candidate_terms(None), [])

    def test_empty_string(self):
        self.assertEqual(split_candidate_terms(""), [])

    def test_underscores_replaced(self):
        result = split_candidate_terms("some_drug_name")
        self.assertEqual(result[0], "some drug name")


class StableTextHashTests(unittest.TestCase):
    def test_deterministic(self):
        h1 = stable_text_hash("test")
        h2 = stable_text_hash("test")
        self.assertEqual(h1, h2)

    def test_length(self):
        self.assertEqual(len(stable_text_hash("anything")), 12)

    def test_hex(self):
        h = stable_text_hash("hello")
        int(h, 16)  # Should not raise


class ValidateDownloadUrlTests(unittest.TestCase):
    """Tests for validate_download_url – scheme, host, and IP guards."""

    # -- scheme checks --------------------------------------------------------

    def test_rejects_ftp_scheme(self):
        with self.assertRaises(ValueError):
            validate_download_url("ftp://api.fda.gov/data.json")

    def test_rejects_file_scheme(self):
        with self.assertRaises(ValueError):
            validate_download_url("file:///etc/passwd")

    def test_rejects_http_for_public_host(self):
        with self.assertRaises(ValueError):
            validate_download_url("http://api.fda.gov/data.json")

    # -- hostname allow-list --------------------------------------------------

    def test_accepts_known_openfda_host(self):
        # Should not raise for a known host with https scheme.
        validate_download_url("https://api.fda.gov/download.json")

    def test_accepts_known_github_host(self):
        validate_download_url("https://github.com/owner/repo/archive/main.zip")

    def test_accepts_known_zenodo_host(self):
        validate_download_url("https://zenodo.org/api/records/12345")

    def test_accepts_known_ebi_host(self):
        validate_download_url("https://ftp.ebi.ac.uk/pub/databases/chembl/")

    def test_accepts_known_pharmgkb_host(self):
        validate_download_url("https://api.pharmgkb.org/v1/download/file/data/test.zip")

    def test_rejects_unknown_host(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://evil.example.com/malware.bin")

    def test_rejects_empty_hostname(self):
        with self.assertRaises(ValueError):
            validate_download_url("https:///path")

    # -- IP-literal checks ----------------------------------------------------

    def test_rejects_loopback_ip(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://127.0.0.1/evil")

    def test_rejects_private_ip(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://192.168.1.1/evil")

    def test_rejects_link_local_ip(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://169.254.1.1/evil")

    def test_rejects_metadata_endpoint(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://169.254.169.254/latest/meta-data/")

    def test_rejects_private_10_net(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://10.0.0.1/evil")

    # -- custom allow-list override -------------------------------------------

    def test_custom_host_set_accepted(self):
        hosts = frozenset({"custom.example.com"})
        validate_download_url("https://custom.example.com/data", allowed_hosts=hosts)

    def test_custom_host_set_rejected(self):
        hosts = frozenset({"custom.example.com"})
        with self.assertRaises(ValueError):
            validate_download_url("https://api.fda.gov/data", allowed_hosts=hosts)

    # -- IPv6 loopback --------------------------------------------------------

    def test_rejects_ipv6_loopback(self):
        with self.assertRaises(ValueError):
            validate_download_url("https://[::1]/evil")


if __name__ == "__main__":
    unittest.main()
