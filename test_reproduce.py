"""Check portability, freshness, and rejection of altered recorded requests."""
import copy
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import reproduce as r
from capture_base import checked


class ReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.temp.name) / "objects"
        cls.manifest, cls.commit = r.import_package(r.PACKAGE, cls.repo)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_complete_package_and_counts(self):
        jobs = self.manifest["jobs"]
        self.assertEqual(len(jobs), 48)
        self.assertEqual(sum(not j["skip"] for j in jobs), 32)
        self.assertNotIn("base", r.entries(self.repo, self.manifest["portable_image"]))
        self.assertEqual(len([n for n in r.entries(self.repo, self.manifest["portable_image"])
                              if n.startswith("layer")]), 23)

    def test_changed_input_is_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        row = manifest["jobs"][0]
        altered = r.change(self.repo, row["original_request"], "command", "blob",
                           r.blob(self.repo, b"echo tampered"))
        row["original_request"] = altered
        with self.assertRaisesRegex(ValueError, "changed tool or inputs"):
            r.validate(self.repo, manifest, self.commit)

    def test_fresh_changes_only_salt(self):
        request = self.manifest["jobs"][0]["request"]
        fresh = r.change(self.repo, request, "salt", "blob", r.blob(self.repo, b"new-run"))
        self.assertNotEqual(request, fresh)
        before, after = r.entries(self.repo, request), r.entries(self.repo, fresh)
        self.assertNotEqual(before.pop("salt"), after.pop("salt"))
        self.assertEqual(before, after)

    def test_existing_directory_refused(self):
        with self.assertRaises(FileExistsError):
            r.import_package(r.PACKAGE, self.repo)

    def test_manifest_substitution_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            (package / "requests.bundle").symlink_to(r.PACKAGE / "requests.bundle")
            (package / "commit").write_bytes((r.PACKAGE / "commit").read_bytes())
            data = copy.deepcopy(self.manifest)
            data["jobs"][0]["expected_result"] = "0" * 40
            (package / "manifest.json").write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "Manifest differs"):
                r.import_package(package, package / "import")

    def test_registry_digest_checked(self):
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            checked(b"wrong image", "0" * 64)

    def test_forged_receipt_is_not_expected_result(self):
        row = next(j for j in self.manifest["jobs"] if j["name"] == "execution-audit-result-swap")
        audit = next(j for j in self.manifest["jobs"] if j["name"] == "execution-audit")
        publish = next(j for j in self.manifest["jobs"] if j["name"] == "execution-publish")
        self.assertEqual(row["expected_result"], audit["expected_result"])
        self.assertNotEqual(row["expected_result"], publish["expected_result"])

    def test_unobserved_and_live_requests_not_automatically_run(self):
        jobs = {r["name"]: r for r in self.manifest["jobs"]}
        self.assertTrue(jobs["execution-audit-substitute"]["skip"])
        self.assertIsNone(jobs["execution-audit-substitute"]["expected_result"])
        self.assertTrue(jobs["retry-safe-1"]["skip"])
        self.assertTrue(jobs["replay-live-fresh"]["skip"])
        self.assertFalse(jobs["replay-snapshot-fresh"]["skip"])

    def test_lost_reply_retains_request_and_is_not_retried(self):
        row = next(j for j in self.manifest["jobs"] if j["name"] == "execution-audit")
        real_git = r.git
        def offline_git(repo, *args, **kwargs):
            if args[0] in ("push", "fetch"):
                return b""
            return real_git(repo, *args, **kwargs)
        with patch.object(r, "git", side_effect=offline_git), patch.object(
                r, "urlopen", side_effect=TimeoutError("lost reply")) as call:
            with self.assertRaises(TimeoutError):
                r.run_job(self.repo, "http://unused.invalid", row, True)
            self.assertEqual(call.call_count, 1)
        record = json.loads((self.repo / (row["request"] + ".json")).read_text())
        self.assertIn("outcome unknown", record["status"])
        self.assertEqual(r.git(self.repo, "rev-parse",
                              "refs/rerun/requests/" + row["request"]).decode().strip(), row["request"])

    def test_different_result_is_reported(self):
        row = next(j for j in self.manifest["jobs"] if j["name"] == "execution-audit")
        other = next(j for j in self.manifest["jobs"] if j["name"] == "execution-publish")
        real_git = r.git
        def offline_git(repo, *args, **kwargs):
            if args[0] in ("push", "fetch"):
                return b""
            return real_git(repo, *args, **kwargs)
        with patch.object(r, "git", side_effect=offline_git), patch.object(
                r, "urlopen", return_value=io.BytesIO(("tree " + other["expected_result"]).encode())):
            result = r.run_job(self.repo, "http://unused.invalid", row, False)
        self.assertFalse(result["matches"])
        self.assertTrue(result["diff"])
        self.assertNotEqual(result["submitted_request"], row["request"])
