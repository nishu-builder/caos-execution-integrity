# Recorded validation

Eight experiments contain **52 scenarios**, including **15 added scenarios** for history, retries, and read access. All matched their expected outcomes in a combined run against a real Caos stack.

| Experiment | Scenarios | Result |
| --- | ---: | --- |
| Execution | 15 | Protected dispatch blocks selected attacks; direct bypass and a lying trusted signer remain visible |
| Evaluation | 6 | Deleting a test makes unchanged broken code pass only under the weakened test set |
| Delegation | 5 | Scoped publication preserves a sibling policy and rejects a wrong destination or stale parent |
| Replay | 6 | Cached answers, fresh queries, and captured-input replays produce distinguishable outcomes |
| Monitoring | 5 | Truncation, silent effects, and false alarms expose distinct monitoring failures |
| History | 4 | Equal initial/final trees conceal an intermediate effect; a pinned tip exposes a rewritten reference |
| Retries | 5 | A lost response produces duplicate effects without idempotency; stable keys prevent the tested duplicate and reject changed payloads |
| Read access | 6 | A known object remains readable outside a narrow input tree; a gateway rule is bypassed through the direct route |

These are scenario counts, not distinct worker counts. Several cases compare different observations of the same execution. The execution experiment also includes three live process cases and six permission probes.

## Provenance

- Run: `20260914T050757Z-88311d95` (UTC).
- Tested execution source: `7bad8e74365d07c177214f5ddeec0c48ccef093f`.
- Source tree: `4d400c0789b939d58d620c8600c57628e4d063cc`.
- Caos revision: `5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3`.
- Evidence commit: `72079e264ceed5d359525f4ac7a84d77b838834a`.
- Evidence branch: [evidence/gallery-20260914T050757Z-88311d95](https://github.com/nishu-builder/caos-execution-integrity/tree/evidence/gallery-20260914T050757Z-88311d95).

Subsequent changes package the measured data, prose, and validation notes. The fixture execution code is unchanged.

## Checks

- All eight experiments ran together; read access also ran individually.
- **28 unit tests passed**, including the six retry-ledger cases and script-free, escaped article rendering.
- Original and current evidence bundles imported into empty Git repositories, passed Git object checks, and verified without a Caos server.
- Negative checks rejected a substituted history anchor, a concealed duplicated effect, and a fabricated gateway verdict.
- The plain article worked with JavaScript disabled: eight sections, 52 expandable cases, existing and new fragment links, and desktop/mobile layouts.
- Temporary HTTP services and lab containers were removed after use.

GitHub Actions runs the same unit and offline evidence checks. Repeat them with `python3 -m unittest -v` and `python3 check_sample.py` after installing the locked dependencies.

## Evidence

[Read the article](https://nishu-builder.github.io/caos-execution-integrity/) · [Raw results](docs/gallery/report.json) · [Bundle](docs/gallery/evidence.bundle) · [Execution receipt public keys](docs/gallery/trust.json)

The history commits are operator-created records, the idempotency ledger is in memory, and the private canary is fake fixture data. Verification checks the retained evidence's consistency; it does not independently attest a trusted component's honesty. External base-image bytes are not included in the bundle.

## Portable Git-object reruns (2026-09-14)

All 32 self-contained worker jobs were rerun with fresh salts from an empty client Git repository using the portable package. Every returned result tree matched the original recorded result. The image contains all 22 original base layers plus the original Caos overlay; there is no external base-image reference. The same existing Caos server was used; this was not a newly provisioned server or a different kernel.

The final runner source was 49fefbd5fae5e5599cd7902c6457c072b6b71419. The [machine-readable rerun record](docs/rerun/validation.json) includes original, portable, and submitted requests and expected and returned results. Their Git objects are published on the [evidence/rerun-20260914 branch](https://github.com/nishu-builder/caos-execution-integrity/tree/evidence/rerun-20260914), pinned by [validation-commit](docs/rerun/validation-commit).

The portable package was imported and checked in an empty repository. Verification checks that the original tool and inputs are unchanged, that the portable image is the imported base plus original overlay, and that every required Git object is present. The known-hash access job explicitly uploads its fake canary. Two exact-request invocations also returned matching results; exact mode is allowed to reuse the cache.

38 unit tests pass, including altered-input rejection, manifest replacement, a forged receipt's result being excluded from expectations, lost-response request retention without retry, and different-result detection. The existing 15-case and 52-case evidence checks also pass. These checks establish consistency and observed rerun behavior, not independent runner attestation.
