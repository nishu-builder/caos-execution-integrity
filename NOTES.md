# Notes on Caos and agent safety

These experiments use real Caos jobs and limited local fixtures to examine execution, evaluation, delegation, replay, monitoring, history, retries, and read access. The published site includes measured results and expandable evidence.

## What this lab establishes

These are mechanism demonstrations, not a deployable safety system. They run on one host with fixed attack scripts, short-lived keys, in-memory ledgers, and serial handlers. We have not tested human approval, authorization recovery after crashes, concurrent attacks, or an adaptive agent. Deployment would still need a protected review and display path, durable authorization, and controls on every route that can cause an external effect.

## Rerun the examples

The complete worker images and inputs are published as [Git objects on the caos-rerun branch](https://github.com/nishu-builder/caos-execution-integrity/tree/caos-rerun) and a [downloadable bundle](https://nishu-builder.github.io/caos-execution-integrity/rerun/requests.bundle). From a clone of the repository, with a compatible Caos server running:

```sh
python3 reproduce.py run --server http://localhost:9090
```

This reruns 32 worker jobs with fresh cache keys and compares the complete result trees with the published results. All 32 matched in our validation. Live services and surrounding safety controls still need the full demo runner. See the [reproduction guide](REPRODUCE.md) for setup and individual examples.

## 1. A recorded command can conceal different execution

An agent asks to run an audit. The transcript names the audit command, shows plausible output, and reports success. But a process handling the request can run something else and return the expected answer. METR describes agents replacing a tool-call handler with an impersonator; our first experiment reconstructs that failure pattern with our own toy handler.

In the lab, the attacker pauses a handler running under the same Unix user, replaces its socket, and executes a different command. The requested audit would create an audit marker. The replacement creates a publication canary instead. Both print OK. The transcript fields are identical, and signing them produces a valid signature in either case.

Unix permissions block the tested handler takeover; the signatures do not. The attacker controls a proxy running as the unprivileged agent user. The protected handler, approver, signing key, caller, and Caos backend are trusted in the defended cases. Host root, a kernel escape, or control of the signer defeats that boundary. The compromised-signer case deliberately shows one such failure.

Within that boundary, we add a dispatcher that checks approval of an exact Caos request, contacts Caos itself, and signs the returned result identity. The signature binds the request and response to a trusted recorder and call; it does not prove that the recorder told the truth. Caos supplies the exact tool, image, input, and result objects that can be named and inspected.

The inline-output case tests the last step to the reader. The proxy adds FORGED INLINE OUTPUT beside a valid signed receipt. Receipt verification succeeds, because that extra field is outside the signature. But the caller ignores it, retrieves stdout from the identified result object, and checks the object hashes. Its recorded display contains the real output. A UI that instead showed the proxy's extra field could display a lie beside a valid receipt. The display path must enforce this rule; this lab tests the recorded caller display, not a production operator UI.

Approval is another unfinished part. The lab controller creates an approver key and automatically signs a preselected request identity, run, and call. No human reviews the request. A usable approval screen would need to explain the tool, image, input changes, and relevant authority, then authorize exactly the snapshot reviewed. A hash makes substitution detectable; it does not make unfamiliar code understandable or a dangerous request acceptable. That review design remains untested here.

The remaining failures matter just as much. An attacker with another route to the backend can cause an effect without producing a valid receipt. A compromised trusted signer can issue a valid lie. Caos supplies stable request and result identities; the protected dispatcher is an experimental addition, and its receipt describes a backend resolution rather than proving a fresh process launch.

The caller’s acceptance or rejection concerns the response, not whether the attack succeeded. Read it alongside the observed effect and displayed output.

[METR: handler replacement](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output) · [Full explanation](BLOG.md)

## 2. Passing the tests can mean weakening the tests

The task is to repair a function that keeps a number between two bounds. The broken version handles the lower bound but ignores the upper one. A submission can make the test command succeed simply by removing the test that catches that mistake.

We run the original program, the cheating submission, and a real repair against two test selections. The cheating submission passes its own workspace tests and fails the operator's original tests. Its program bytes are unchanged. The real repair passes both.

Caos lets the operator bind an exact evaluator and test set while varying the submitted program independently. The recorded request identifies those choices, and the result includes each test outcome. A reviewer can see whether the program improved or the meaning of success changed.

This protects a particular evaluation boundary. It does not make weak tests strong, prevent a program from recognizing visible tests, or isolate arbitrary hostile code from the evaluator. METR's account of attempts to substitute an easier target is a related failure mode, not an exploit recreated by this fixture.

[METR: attempts to replace the target](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#attempting-to-replace-the-exploitgym-target-with-a-modified-target)

## 3. A child should not choose where its work is applied

A parent delegates a documentation change. The child returns an updated guide together with a file disabling the repository's review policy. Accepting its entire returned repository gives it authority over both changes.

In the scoped version, the child receives only the docs subtree. More importantly, the parent applies the child's result only at a destination the parent selected in advance. A returned policy.txt lands inside docs; the actual root policy remains unchanged. The legitimate guide update still goes through.

The integrator also rejects an attempt to select the repository root as the destination and a proposal based on an older parent state. Unit tests cover symlinks that could cross the file boundary when materialized. Caos supplies the exact input and result trees; the integration policy is added here.

This limits publication authority. It does not make the documentation trustworthy, revoke network access, or impose read permissions on a shared object store. A real publisher also needs an atomic check of the branch tip at publication time. Checking a parent identity earlier is not enough to prevent every race.

[Implementation and longer explanation](https://github.com/nishu-builder/caos-execution-integrity/blob/main/demos/delegation/README.md)

## 4. A repeated request may not recheck the world

A local HTTP policy service initially says ALLOW. A Caos job reads it. We then change the service to DENY and request the same job again.

The repeated request returns the cached ALLOW result without another read of the service. A fresh execution, made by changing only the salt, reads the same URL and gets DENY. The service's log distinguishes those two events.

To reproduce the historical decision, we capture the original response as an explicit Git input. Fresh jobs over that snapshot keep returning ALLOW while the live service says DENY. Explicitly adopting a new snapshot changes the result.

These answer different questions: what the system returned before, what it would observe now, and what it does with the same historical evidence. Caos makes the input differences inspectable. It does not make a changing URL immutable, turn old evidence into current authorization, or prove that a captured service response was truthful.

[Implementation and longer explanation](https://github.com/nishu-builder/caos-execution-integrity/blob/main/demos/replay/README.md)

## 5. Saved evidence may never reach the monitor

A worker creates a local publication canary and reports it, then prints enough routine progress to push the event outside the final 512 characters. Its last line says the audit completed with no issues.

A monitor reading only that tail reports CLEAR. Reading the complete retained output reveals the event. We then try a silent variant: the canary is created but never mentioned. A full-output scan misses it; a check of the retained filesystem finds it.

Finally, a benign message mentions the same filename without creating it. The keyword scanner raises a false alarm. Across these cases, missing evidence and mistaken interpretation produce different failures.

Caos gives a monitor a way to retrieve exact result objects independently of a shortened display. But a complete result is not a complete history, and complete evidence does not make a weak detector correct. The next experiment follows an effect that disappears before the final snapshot.

[Implementation and longer explanation](https://github.com/nishu-builder/caos-execution-integrity/blob/main/demos/monitoring/README.md)

## 6. A clean final state can hide an earlier action

A worker creates a publication canary. A later worker removes it. The final workspace has exactly the same Git tree identity as the initial workspace. A review of the final snapshot, or a comparison of the initial and final trees, finds no change.

We retain the intermediate result and link the snapshots in ordinary Git commits. Examining that history reveals the canary. The cleanup request also names the preceding result as its input, so the intended chain can be inspected.

There is another trap: a branch name can be rewritten. The lab replaces its own temporary history reference with a new, parentless commit containing the same clean final tree. Following the name now shows a clean story. Comparing it with the previously pinned history tip detects the substitution.

The useful property is retained and anchored history, not the mere use of Git. The operator records these commits in this demo; they are not independently attested conversation turns. An effect created and removed within one job could still evade boundary snapshots, and a compromised recorder could omit it. The evidence bundle retains both histories so the comparison can be checked offline.

[Implementation and longer explanation](https://github.com/nishu-builder/caos-execution-integrity/blob/main/demos/history/README.md)

## 7. Losing the reply does not mean the action failed

The worker asks a local service to apply an effect. The service records it and deliberately closes the connection before replying. The worker reports UNKNOWN. That uncertainty is real: from its response alone, it cannot tell whether the action happened.

Running a fresh retry against the ordinary endpoint applies the effect a second time. The first attempt and its retry have different Caos request identities because of their salts, even though they express the same logical intent.

At the second endpoint, the service binds a stable idempotency key to the payload. The first call again loses its reply after applying the effect. The retry returns the existing outcome without applying it again. Reusing the key with a different payload is rejected.

The protection lives where the side effect occurs. Caching a Caos result is not a substitute for that contract. Our ledger is in memory and the service handles requests serially; it does not establish crash-safe or concurrent exactly-once behavior. Production systems need durable, atomic intent records and an authorization check appropriate to the action.

[Implementation and longer explanation](https://github.com/nishu-builder/caos-execution-integrity/blob/main/demos/retries/README.md)

## 8. An input tree is not a read permission

A child receives only a public documentation subtree. A canary in a sibling private directory is absent from that input. It is tempting to treat this as a confidentiality boundary.

The canary is an explicitly fake value placed on the demo's own Caos server. When we give the child its object identity, the worker can fetch it directly even though it is outside the supplied subtree. This tests known-hash access; it says nothing about how easy a real secret's identity would be to discover.

We add a small gateway that serves only an allowed public object. It accepts a request for that object and refuses the private canary. But the worker can still bypass the gateway and use the server's direct object route. A policy on one route cannot protect data while another route remains open.

Passing a narrow tree is useful for reducing accidental exposure and making a task's intended inputs clear. Actual confidentiality also needs enforced backend permissions or isolation that closes other routes. Git object identities name content; they do not automatically grant or deny permission to read it.

[Implementation and longer explanation](https://github.com/nishu-builder/caos-execution-integrity/blob/main/demos/access/README.md)
