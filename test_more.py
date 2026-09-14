import json
from pathlib import Path
import tempfile
import unittest
from demo_service import Ledger
from blog import render


class RetryTests(unittest.TestCase):
    def test_unknown_reply_can_follow_an_effect(self):
        ledger=Ledger()
        self.assertEqual(ledger.post("unsafe","intent","payload"),(201,"applied",True))
        self.assertEqual(len(ledger.effects["unsafe"]),1)

    def test_unsafe_retry_duplicates_effect(self):
        ledger=Ledger()
        ledger.post("unsafe","intent","payload")
        ledger.post("unsafe","intent","payload")
        self.assertEqual(len(ledger.effects["unsafe"]),2)

    def test_safe_retry_reuses_intent(self):
        ledger=Ledger()
        ledger.post("safe","intent","payload")
        self.assertEqual(ledger.post("safe","intent","payload"),(200,"already applied",False))
        self.assertEqual(len(ledger.effects["safe"]),1)

    def test_same_key_cannot_authorize_different_payload(self):
        ledger=Ledger()
        ledger.post("safe","intent","payload")
        self.assertEqual(ledger.post("safe","intent","other")[0],409)
        self.assertEqual(ledger.effects["safe"],[{"key":"intent","body":"payload"}])

    def test_distinct_intents_are_not_deduplicated(self):
        ledger=Ledger()
        ledger.post("safe","one","payload")
        ledger.post("safe","two","payload")
        self.assertEqual(len(ledger.effects["safe"]),2)

    def test_missing_key_does_not_apply_effect(self):
        ledger=Ledger()
        self.assertEqual(ledger.post("safe","","payload")[0],400)
        self.assertEqual(ledger.effects["safe"],[])


class BlogTests(unittest.TestCase):
    def report(self):
        return dict(run_id="test",source_commit="a"*40,caos_revision="b"*40,asset_prefix="",
                    demos=[dict(id="monitoring",cases=[dict(label="<script>alert(1)</script>",verdict="CLEAR")])])

    def test_evidence_is_escaped_and_readable_without_scripts(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"index.html"
            render(self.report(),target,include_evidence=True)
            text=target.read_text()
            self.assertNotIn("<script",text)
            self.assertIn("&lt;script&gt;",text)
            self.assertIn('id="monitoring"',text)
            self.assertIn("<article",text)
            self.assertNotIn('role="tab"',text)

    def test_blog_separates_problems_from_approaches(self):
        report=json.loads((Path(__file__).parent/"docs/gallery/report.json").read_text())
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/"index.html"
            render(report,target)
            text=target.read_text()
            self.assertEqual(text.count("<h3>Problem</h3>"),8)
            self.assertEqual(text.count("<h3>CAOS</h3>"),8)
            self.assertNotIn('<details class="cases">',text)
            self.assertIn("<code>rm secret.txt</code>",text)

    def test_evidence_link_cannot_execute_script(self):
        report=self.report()
        report["asset_prefix"]="javascript:alert(1)//"
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            render(report,Path(d)/"index.html")


if __name__ == "__main__":
    unittest.main()
