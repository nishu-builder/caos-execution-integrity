# Recorded validation

Run: `20260914T012808Z-8db4c503` (UTC)  
Tested source: `f76fab3e06c2d55a079cccb07306c7d02cc63662`  
Caos revision: `5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3`  
Lab image: `sha256:f00aef2637d45dab6e10eaab35a1b082b3e80ec8a660f096a77c2bfd00536af6`  
Evidence commit: `73a9de2034fe06ebc13e2061dc0444694c2a78a7`  
Evidence branch: [evidence/20260914T012808Z-8db4c503](https://github.com/nishu-builder/caos-execution-integrity/tree/evidence/20260914T012808Z-8db4c503)

The sample was generated on Linux x86_64 with a real Caos stack. Subsequent changes package the sample, refine documentation and report wording, and add verification automation. The execution and cryptographic code are unchanged.

## Results

- **3 process experiments:** identical transcript fields and signatures; the takeover replaces the actual command; Unix-user separation blocks the tested takeover.
- **6 permission probes:** stopping the handler, replacing its socket, changing its configuration, reading its key, opening its memory, and connecting to its private socket all denied.
- **15 Caos experiments:** all matched their expected acceptance and side-effect outcomes.
- **12 unit tests:** signature tampering, identity binding, key substitution, malformed envelopes, misleading inline output, and Git object integrity.
- **Portable evidence:** imported the standalone bundle into an empty Git repository, passed Git object checks, and verified signatures, result contents, fixture mutation, fresh per-case salts, and recorded dispatches without a Caos server.
- **Browser checks:** all three comparison tabs, 15 case rows, and receipt inspection worked on desktop and mobile without script errors or page overflow.
- **Locked runtime:** all 12 unit tests also passed inside the pinned Docker image with networking disabled.
- **Negative evidence checks:** rejected changed trust anchors and output that contradicted its retained result object.

Successful attack cases are intentional results, not test failures. The unrestricted direct route causes the local effect despite receipt rejection. A deliberately compromised signer produces an accepted lie.

## Recheck this sample

After cloning the repository and installing the locked requirements as described in README:

```sh
git fetch origin 'refs/heads/evidence/20260914T012808Z-8db4c503:refs/heads/evidence/20260914T012808Z-8db4c503'
python3 verify.py docs/report.json \
  --witness-key b4d92b222d03427a4611e6806812490d18359ac28da6143a7f6ed81d10ce3f1c \
  --approver-key 5a82731c341237cc07f6ded807f9cc7af40c88e3ed6c19367cd27fc71bcddd0d
```

Or import [docs/evidence.bundle](docs/evidence.bundle) into an empty repository and pass its path with `--repo`.

These keys are the public trust anchors for this published sample. Only use them if you trust the publication. The private keys were generated inside the disposable lab container and were not exported. A replacement report with replacement keys is not evidence of the original run.

[Open the interactive report locally](docs/index.html) or read [the raw report](docs/report.json). The HTML uses no external scripts or services. The bundle retains Git objects by identity; it does not freeze third-party services or certify that the trusted dispatcher was honest.
