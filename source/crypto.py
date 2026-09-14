"""Domain-separated Ed25519 envelopes. Keys never come from the untrusted response."""
import base64
import json
import re
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

DOMAIN = b"caos-execution-integrity-lab-v1\\0"


def canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def private_bytes(key):
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                             serialization.NoEncryption())


def public_hex(key):
    return key.public_key().public_bytes(serialization.Encoding.Raw,
                                        serialization.PublicFormat.Raw).hex()


def sign(key, body):
    return {"body": body, "signature": base64.b64encode(key.sign(DOMAIN + canonical(body))).decode()}


def verify(public, envelope):
    if not isinstance(envelope, dict) or not isinstance(envelope.get("body"), dict):
        raise ValueError("invalid envelope")
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(
            base64.b64decode(envelope["signature"], validate=True),
            DOMAIN + canonical(envelope["body"]))
    except (InvalidSignature, ValueError, KeyError, TypeError) as e:
        raise ValueError("invalid signature") from e
    return envelope["body"]


def verify_receipt(public, envelope, approval):
    body = verify(public, envelope)
    for name in ("run_id", "call_id", "request"):
        if body.get(name) != approval.get(name):
            raise ValueError(f"receipt {name} mismatch")
    if body.get("type") != "resolution" or body.get("schema") != 1:
        raise ValueError("wrong receipt type")
    if body.get("status") != "resolved":
        raise ValueError("dispatcher rejected request: " + str(body.get("reason", "unknown")))
    if not isinstance(body.get("result"), str) or not re.fullmatch("[0-9a-f]{40}", body["result"]):
        raise ValueError("invalid result identity")
    return body
