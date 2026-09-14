import copy
import unittest
from unittest.mock import patch
from crypto import Ed25519PrivateKey, public_hex, sign, verify, verify_receipt
from lab import raw_object
import hashlib


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = public_hex(self.key)
        self.approval = dict(schema=1, type="approval", run_id="run", call_id="call", request="a" * 40)
        self.body = dict(self.approval, type="resolution", status="resolved", result="b" * 40)
        self.receipt = sign(self.key, self.body)

    def test_valid_receipt(self):
        self.assertEqual(verify_receipt(self.public, self.receipt, self.approval), self.body)

    def test_every_signed_field_is_bound(self):
        for field in self.body:
            with self.subTest(field=field):
                envelope = copy.deepcopy(self.receipt)
                envelope["body"][field] = "tampered"
                with self.assertRaises(ValueError):
                    verify_receipt(self.public, envelope, self.approval)

    def test_valid_signature_wrong_occurrence(self):
        for field in ("run_id", "call_id", "request"):
            with self.subTest(field=field):
                approval = dict(self.approval, **{field: "different"})
                with self.assertRaises(ValueError):
                    verify_receipt(self.public, self.receipt, approval)

    def test_wrong_key_even_if_offered(self):
        attacker = Ed25519PrivateKey.generate()
        envelope = sign(attacker, self.body)
        envelope["offered_public_key"] = public_hex(attacker)
        with self.assertRaises(ValueError):
            verify_receipt(self.public, envelope, self.approval)

    def test_unsigned_inline_fields_have_no_authority(self):
        self.receipt["stdout"] = "FORGED"
        self.assertNotIn("stdout", verify_receipt(self.public, self.receipt, self.approval))

    def test_wrong_type_and_status(self):
        for field, value in (("type", "approval"), ("schema", 2), ("status", "rejected")):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    verify_receipt(self.public, sign(self.key, dict(self.body, **{field: value})), self.approval)

    def test_malformed_result_fails_closed(self):
        for value in (None, 4, [], {}, "", "c" * 39, "z" * 40):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    verify_receipt(self.public, sign(self.key, dict(self.body, result=value)), self.approval)

    def test_malformed_envelopes_fail_closed(self):
        for value in (None, [], {}, {"body": []}, {"body": {}, "signature": "?"}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    verify(self.public, value)

    def test_signing_a_lie_does_not_fix_it(self):
        # A receipt has no intrinsic knowledge of the process or side effects.
        lie = sign(self.key, dict(self.body, result="c" * 40))
        self.assertEqual(verify_receipt(self.public, lie, self.approval)["result"], "c" * 40)

    def test_result_object_bytes_are_verified(self):
        raw = b"blob 3\0OK\n"
        oid = hashlib.sha1(raw).hexdigest()
        with patch("lab.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = raw
            self.assertEqual(raw_object("http://unused", oid), ("blob", b"OK\n"))
            urlopen.return_value.__enter__.return_value.read.return_value = b"blob 3\0NO\n"
            with self.assertRaises(ValueError):
                raw_object("http://unused", oid)

    def test_object_size_checked_even_with_matching_hash(self):
        raw = b"blob 100\0OK\n"
        with patch("lab.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = raw
            with self.assertRaises(ValueError):
                raw_object("http://unused", hashlib.sha1(raw).hexdigest())

    def test_invalid_object_id_never_reaches_network(self):
        with patch("lab.urllib.request.urlopen") as urlopen:
            with self.assertRaises(ValueError):
                raw_object("http://unused", "../run")
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
