# Rerun the Caos jobs from Git

The published package contains the tool scripts, input trees, complete worker image layers, and expected results. You can send those requests to your own Caos server without rebuilding the demos or contacting the original machine's registry.

## Quick start

You need Git, Python 3.10+, and a running Linux x86_64 Caos server compatible with [the recorded revision](https://github.com/Metta-AI/caos/tree/5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3). The client computer needs neither Docker nor Nix nor the Caos CLI. Provisioning a Caos server is separate.

```sh
git clone https://github.com/nishu-builder/caos-execution-integrity.git
cd caos-execution-integrity

# First compare the broken, cheated, and fixed submissions.
python3 reproduce.py run --server http://127.0.0.1:9090 --only evaluation

# Or rerun every job that does not require a live fixture.
python3 reproduce.py run --server http://127.0.0.1:9090
```

Replace the URL with your server's address. The script imports the package into a new directory under `.runtime/`, checks its Git objects, pushes the selected requests, and compares each returned tree with its published result. `MATCH` means the entire result tree has the same Git identity, including output and returned files. It does not mean an attack was prevented: several expected results deliberately demonstrate failures.

The default adds a new random salt to each request, so an old request's cached answer cannot satisfy it. The image, worker, and input objects stay fixed. To submit the published portable request unchanged, add `--exact`; that may reuse a cached result.

```sh
python3 reproduce.py list
python3 reproduce.py verify
python3 reproduce.py run --server http://127.0.0.1:9090 --only monitoring
python3 reproduce.py run --server http://127.0.0.1:9090 --only execution-audit
```

`verify` needs no server. Each run retains its requests and results as Git refs and writes `rerun.json` with the original, portable, and submitted request identities, expected and actual results, and comparison. Set `--workdir NEW_DIRECTORY` to choose where these go. Existing directories are refused.

## What is included?

| Experiment | Jobs runnable from the package | What still needs the full demo |
| --- | --- | --- |
| Execution | 11 recorded audit, publication-canary, custom-tool, and changed-workspace jobs | Handler takeover, signatures, approval decisions, and network restrictions |
| Evaluation | All 6 evaluation jobs | Nothing for the recorded worker comparisons |
| Delegation | All 3 child jobs | The operator's subtree integration and rejection rules |
| Replay | All 3 captured-input jobs | The live service changing its response and observation of cache reuse |
| Monitoring | All 3 worker jobs | The different monitors that inspect those results |
| History | Both write and cleanup jobs | The operator's history construction and rewritten-ref comparison |
| Retries | Requests are retained, but not run by this shortcut | The effect service, lost replies, ordering, and idempotency ledger |
| Read access | 4 direct-input and known-hash jobs | The HTTP gateway and its permission decisions |

That is **32 runnable jobs**, drawn from the eight experiments' 52 cases. Several cases inspect one worker result with different policies, so cases and jobs are different counts. The remaining 16 requests are listed with an explanation: nine require temporary HTTP services, and seven were prepared but never executed in the original experiment.

The read-access jobs include only the demonstration's explicitly fake private canary. The script supplies that object separately for the known-hash reads; it does not depend on the original server already holding it.

Use [the full demo runner](README.md#run-the-demos) to reproduce host policies and live service interactions. The worker rerun does not reproduce those surrounding controls or mint new execution receipts.

## Fetch the objects with ordinary Git

The same package is published as the `caos-rerun` branch. Its tip is pinned in [docs/rerun/commit](docs/rerun/commit). You do not have to check out that branch: its tree is a collection of runnable objects, not a source checkout.

```sh
git fetch origin caos-rerun
git rev-parse FETCH_HEAD
cat docs/rerun/commit
# The two commit IDs should match.

git show FETCH_HEAD:manifest.json
git ls-tree FETCH_HEAD:requests
```

[The standalone bundle](https://nishu-builder.github.io/caos-execution-integrity/rerun/requests.bundle) contains the same closure and can be imported into an empty repository. [The manifest](docs/rerun/manifest.json) names each request, its original request, expected result, and any missing live fixture.

A raw request is already runnable; no expression evaluation or source checkout is needed. For example, after checking that the fetched commit matches the pinned value:

```sh
request=$(git rev-parse FETCH_HEAD:requests/evaluation-cheated-protected)
server=http://127.0.0.1:9090
git push "$server" "$request:refs/caos/req/$request"
curl --fail --show-error "$server/run?req=$request"
```

This unchanged request may hit the cache. The Python shortcut is preferable when you want a fresh key, result comparison, and retained records.

## What changed from the original recording?

The original worker image referred to a base in the original machine's registry. A Git bundle containing that locator alone was insufficient for another machine.

We captured that exact base's 22 layers, checking the registry manifest and blob SHA-256 digests, and imported them with Caos's `import-image`. We appended the original worker overlay and kept the original image configuration. The resulting image has **no external base reference**: its files, symlinks, executable bits, and Caos metadata sidecars are Git objects.

Consequently, portable requests have a different `base` object from the historical requests. The package keeps both. Verification checks that every other argument is unchanged; a fresh rerun changes only `salt` on top of that. These are explicitly derived requests, not claims to have rerun the historical request hash unchanged.

The expected result identities come from the original experiment's actual worker observations, including the actual result in tampering cases, rather than a forged receipt or displayed answer. Fresh reruns compare against those identities.

This packages the worker filesystem, not the server, Linux kernel, or every property of the execution environment. A compatible Caos runner is still required. Git verifies bytes and closure; it does not attest that a server honestly executed them, and it does not make live external state reproducible.

## Maintainer packaging

`pack_reproduction.py` takes the Git tree returned by importing the full original base image, combines it with the retained overlay, and exports the manifest, bundle, and `caos-rerun` ref. It refuses unexpected additional worker bases. `capture_base.py` downloads the pinned base from a registry reachable by the maintainer, checks all digests, and makes the Docker archive for import.

```sh
python3 capture_base.py --registry http://127.0.0.1:5000 --output .runtime/captured-base
caos-cli import-image .runtime/captured-base/base.tar
python3 pack_reproduction.py --base-image THE_RETURNED_TREE
python3 reproduce.py verify
```

The package itself is about 25 MB. Readers download it from Git; they never need access to that original registry.
