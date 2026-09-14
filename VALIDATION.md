# Recorded validation

The shared gallery contains **five demos and 37 scenarios**. All matched their expected outcomes on a real Caos stack. Successful attacks and false alarms are intentional observations, not hidden test failures.

| Demo | Scenarios | Measured result |
| --- | ---: | --- |
| Execution | 15 | Same signed transcript with different effects; protected dispatch blocks selected attacks; bypass and trusted-signer failures remain visible |
| Evaluation | 6 | Deleted test makes unchanged broken code pass only under workspace-selected tests |
| Delegation | 5 | Broad authority changes a sibling policy; scoped integration preserves it and rejects wrong destination/stale parent |
| Replay | 6 | Cached ALLOW survives a service change; fresh live execution returns DENY; captured-input replays remain stable |
| Monitoring | 5 | Tail truncation and silent effects evade selected monitors; full evidence helps; benign text still produces a false alarm |

The execution demo also includes three live process experiments and six permission probes. Monitoring compares five configurations over three executions. Delegation reuses a child's real proposal to test two integration rejections. These counts are scenarios, not distinct process launches.

## Provenance

- Run: `20260914T044729Z-ae4a4abd` (UTC).
- Tested execution source: `401a0d305e46d6c90d8288be4ae53228ecc06d7f`.
- Source tree: `8c20d86cac591a1f5a22debc4000d280ee41bfb7`.
- Caos revision: `5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3`.
- Evidence commit: `35166b9e2387dc3ade8a94f263823fb6e0ca241d`.
- Evidence branch: [evidence/gallery-20260914T044729Z-ae4a4abd](https://github.com/nishu-builder/caos-execution-integrity/tree/evidence/gallery-20260914T044729Z-ae4a4abd).

Later edits package the measured sample and strengthen offline verification; the fixture execution code is unchanged.

## Checks performed

- All five demos ran together through `demo.py run --only all`.
- Monitoring also ran individually through the same command interface.
- **20 unit tests passed**, including signature tampering, object integrity, scoped publication, stale parents, invalid destinations, nested symlinks, and replay input comparison.
- The original and combined evidence bundles each imported into an empty Git repository, passed Git object checks, and verified offline without a Caos server.
- Modified evaluation outcomes, delegated policy results, service-read observations, and monitor views were rejected by the verifier.
- Browser checks passed for all five tabs and 37 rows, evidence inspectors, the original transcript comparison, keyboard navigation, direct links, and mobile layouts.
- Temporary policy-service containers were removed after their runs.

Run `python3 check_sample.py` after installing the locked requirements to repeat the offline checks. GitHub Actions runs the unit tests and sample verification on updates.

## Inspect and reuse

- [Interactive gallery](https://nishu-builder.github.io/caos-execution-integrity/).
- [Combined raw results](docs/gallery/report.json).
- [Standalone evidence bundle](docs/gallery/evidence.bundle).
- [Execution receipt public keys](docs/gallery/trust.json).
- [Original sample validation](docs/legacy-validation.md).

The receipt keys authenticate statements by the execution demo's witness. The remaining demos retain operator observations and Git objects. Verification checks internal consistency against these published anchors; it cannot establish that a compromised witness, operator, runner, or external service was honest. The image base is pinned by digest, but its external bytes are not included in the bundle.
