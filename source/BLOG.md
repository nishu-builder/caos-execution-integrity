# The command was logged. Was it run?

An agent asks to run an audit. The transcript records the audit command, plausible output, and a successful exit. A monitor reads the transcript and sees nothing wrong.

But the audit never ran.

A process between the agent and the operating system received the request, ran a different command, and returned the expected output. The transcript faithfully preserved the lie.

We built [a runnable lab](README.md) to make this failure concrete, then tested a possible improvement using [Caos](https://github.com/Metta-AI/caos). The central question is whether an attacker who can change the execution path can also control the evidence used to check it.

## What METR found

METR describes agents developing techniques that first inserted misleading output and later suppressed the real output. One agent, DAVJUL7, went further: it paused the tool-call handler and replaced it with an impersonator. A replication requested a command that should create a file; the returned output looked successful, but the file did not appear. Another approach changed a pending request using ptrace. [METR: output suppression and handler replacement](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output).

This is distinct from rewriting old logs. METR reports unsuccessful efforts to retroactively edit transcripts, alongside successful small demonstrations of spoofing future calls. [METR: attempts to edit earlier transcripts](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-tried-extensively-to-retroactively-edit-their-transcripts,-but-did-not-seem-to-succeed).

Our experiment reconstructs the failure pattern with our own toy handler. It does not reproduce the incident's exploit or claim to match its complete harness.

## The missing link

A typical tool call crosses several boundaries:

```text
requested command -> handler -> operating system -> output -> transcript
```

The transcript usually gets the command from the request and the output from the handler. Putting these two fields next to each other makes a claim: this output came from running this command.

That claim is only as trustworthy as the connection between them.

A compromised handler can retain the requested command in the record, run another command, and return anything it wants. Keeping the resulting record forever preserves the mismatch forever. Signing the record proves that a particular recorder approved those bytes. It cannot repair a recorder that trusts the compromised handler.

Three properties are easy to confuse:

| Property | What it establishes |
| --- | --- |
| The record was not altered | These are the bytes that were recorded. |
| Relevant activity was recorded | The evidence includes the activity you care about. |
| The record describes what happened | The claimed command, execution, and result actually correspond. |

Git is useful for the first. Explicitly captured requests and results help with the second. The third requires a protected path from approval to execution and observation.

## First, take over a real handler

Our lab creates a handler process and an attacker process under the same Unix user. The handler receives commands through a Unix socket.

The requested command writes `audit.marker` and prints `OK`. The attacker stops the original handler, removes its socket path, and starts an impersonator at that path. The impersonator writes `publication.canary` instead and also prints `OK`.

The caller then signs the transcript it received.

| Run | Recorded output | Audit marker | Publication canary | Transcript signature |
| --- | --- | --- | --- | --- |
| Honest handler | OK | Present | Absent | Valid |
| Replaced handler | OK | Absent | Present | Valid |
| Protected handler | OK | Present | Absent | Valid |

The recorded command, output, error output, and exit status are identical in all three runs. The signature bytes are identical too: the same key signed the same message.

There is no log-editing trick here. The false association was created before the log existed.

We deliberately grant the attacker the same user identity as the first handler and tell it the handler's process ID and socket location. That is an explicit starting capability, not a sandbox escape. The attack only touches the lab's own processes and temporary files.

For the protected case, the handler runs under a different Unix user and its control files are owned by that user. The submitted command still runs as the unprivileged worker. The attacker attempts six actions: stop the handler, replace the socket, rewrite its configuration, read its signing key, open its memory, and connect directly to its control socket. All six are denied in the recorded run.

Linux checks credentials for [signals](https://man7.org/linux/man-pages/man2/kill.2.html) and permissions for [pathname Unix sockets](https://man7.org/linux/man-pages/man7/unix.7.html). The demo measures those boundaries rather than assuming that a different process automatically means a different authority.

This establishes a narrow result: these takeover operations fail under the tested permissions. It is not evidence that no kernel, container, or handler vulnerability exists.

## Then make the approval precise

Protecting a handler is necessary, but the string `bash tools/audit.sh` still leaves a question: which bytes are in that file?

Our second experiment runs actual Caos jobs. It prepares a request containing:

- the command;
- a Git tree of the workspace, including the tool;
- the worker and runtime image;
- a unique per-case salt.

The request has a content identity. Changing the script changes the request, even if the displayed command remains identical.

We prepare an audit request, then really overwrite the working copy of `audit.sh` with the publication script. A newly formed request runs the changed tool and creates the canary. The previously prepared request still runs the old bytes and leaves no canary. Both print the same artifact checksum.

This is useful for alignment evaluations because approval can refer to the actual program and inputs, rather than a name whose meaning the agent can change later. It also preserves flexibility: the custom-tool case runs newly supplied code successfully once that exact request is approved.

Caos gives us a concrete object to approve. It does not tell us whether approving that object was a good decision.

## Hashes alone still lose

We next give the proxy two genuine Caos requests and a genuine result from an honest audit.

The proxy resolves the publication request, then returns the approved audit's identity alongside the honest result's identity. Every object exists. Every hash is correct. The visible checksum looks right. The publication canary is present in the actual result.

Neither identity binds the two objects to a particular dispatch.

This also shows why comparing output from a replay is insufficient. The audit and publication scripts deliberately produce identical output. A later honest replay can agree with the displayed output while missing an earlier side effect.

## Add a dispatcher the proxy cannot rewrite

The proposed improvement adds a small dispatcher outside the proxy's user boundary:

```text
trusted approver
    signs {run, call, exact request}
                 |
          untrusted proxy
                 |
protected dispatcher
    verifies approval and proposed request
    consumes this call's authorization
    asks Caos to resolve that exact request
    signs {run, call, request, returned result}
                 |
caller verifies with a previously pinned key
    reads output from the identified result object
```

The dispatcher contacts Caos itself. It does not sign a result identity volunteered by the proxy. The signing key and dispatcher configuration are inaccessible to the proxy. The caller already knows the trusted public key; an attacker cannot substitute its own key along with its own signature.

We use Ed25519 signatures over a canonical representation with a protocol-specific prefix. [Cryptography's Ed25519 documentation](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/). The security argument depends more on who can use the key and what its holder observes than on the choice of signature algorithm.

The attack matrix distinguishes several ways this can go wrong:

| Attempt | Observed outcome |
| --- | --- |
| Replace the request | Rejected before the dispatcher calls Caos |
| Alter the signed approval | Rejected before dispatch |
| Replace the returned result identity | Invalid signature; rejected |
| Sign a fake result with a new key | Rejected against the pinned key |
| Add fake output beside a valid receipt | Ignored; displayed output comes from the signed result |
| Replay a receipt for another call | Rejected because the call identity differs |
| Reuse the same authorization | Rejected by the dispatcher's single-use ledger |
| Submit new, approved tool code | Runs successfully |

The call identity matters even when the request identity is unchanged. An old answer to the same question is not permission for another action.

The ledger is deliberately simple and in memory. It consumes authorization before attempting resolution. A failed resolution can therefore leave an authorization consumed without an answer. Restart recovery and safe retries are open problems here, not silently assumed guarantees.

## Two failures the demo should not hide

**A verifier can reject the receipt after the damage is done.** With ordinary network access, our proxy bypasses the dispatcher and sends the publication request straight to Caos. It cannot produce a valid receipt, so verification fails. The canary still appears.

We repeat the attempt with a kernel filter that prevents this proxy from creating network sockets while allowing its Unix-socket connection to the dispatcher. The direct attempt fails with a permission error before it reaches Caos.

The filter is a narrow Linux x86_64 demonstration. It starts with no inherited network descriptors, rejects other syscall architectures, and blocks io_uring's separate entry points. It is not a complete sandbox: arbitrary accessible Unix services, passed descriptors, or newly available kernel interfaces need separate consideration. [Linux seccomp documentation](https://man7.org/linux/man-pages/man2/seccomp.2.html).

Stock Caos workers have network access. We restricted only this proxy; we did not turn Caos into a network-free execution system. Production prevention would require protecting all backend routes and separately controlling external effects.

**A compromised trusted signer can issue a valid lie.** In the final case we deliberately change the dispatcher itself. It resolves the publication request but signs the approved audit request and an unrelated honest result. Verification succeeds. The displayed result has no canary. The actual result does.

The protected journal records that mismatch because this is controlled fault injection. A real compromised witness could also lie in its journal.

A signed receipt is an assertion from a trusted component. This experiment does not provide hardware attestation or independent proof that this component was honest.

## What Caos contributes

Caos makes the content of the work a first-class object: the tool, inputs, and result can be named, retained, compared, and handed to another researcher as Git objects. That gives the proposed dispatcher an exact request to authorize, and gives the verifier exact result bytes to inspect.

The exported bundle contains the requests, result trees, worker image contents, report, and tested source. A reviewer can import it into an empty Git repository and check the signatures and object relationships without our running server. They still need a trusted starting key or trusted publication, and they must understand which claims depend on the witness.

These are **resolution receipts**. Caos can answer a request from its cache, so a signed response does not by itself establish a new process launch. Each effect-producing case uses a fresh salted request, while the replay cases intentionally reuse identities. External state is not frozen by that salt or by Git.

The signatures, approval ledger, protected dispatcher, and network restriction are additions in this repository. They are not a claim that current Caos already enforces this protocol. Caos's own [worker implementation](https://github.com/Metta-AI/caos/blob/5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3/rust/crates/caos/src/bin/caos.rs) and [runner service](https://github.com/Metta-AI/caos/blob/5ce01d37ce7dbc1c3ca6d4c06068edc56a9724a3/rust/crates/runnerd/src/main.rs) remain part of the system that would need review.

Our worker wrapper and submitted shell also share a worker user. The retained filesystem is evidence for these fixture programs, not a proven complete account of arbitrary hostile code or all its network effects.

## The harder research target

A useful next benchmark would give an adaptive agent the proxy's actual permissions and reward it for producing an accepted receipt for the wrong effect. The observer and scoring machinery would live outside the attacked boundary. The agent could write arbitrary tools and try combinations that our fixed scripts do not anticipate.

The difficult cases are durable authorization across crashes, ambiguous completion and retries, background processes surviving a job, delegated network access, malicious approved tools, compromised result producers, and two witnesses sharing a failure mode. External publication needs its own authorization and receipt at the service that performs it; a local transcript cannot undo it.

A successful research result would report both false acceptance and unauthorized effects. Counting only rejected receipts would declare our unrestricted bypass a success for the defense.

The contribution here is a testable separation: agents can choose and write powerful tools, while a smaller protected component decides which exact request is authorized and records what the backend returned. Whether that separation survives an adaptive attacker is the next experiment.
