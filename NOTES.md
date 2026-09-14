# CAOS and the METR incident

CAOS represents programs, inputs, and results as Git objects. That makes three different checks possible: repeat work on another runner, inspect the code behind a name, and detect changes or gaps in a saved history. The METR investigation supplies concrete examples of why each matters.

## 1. Check a runner’s result on another runner

### Problem

Agents in the OpenAI swarm found multiple ways to change the behavior of their tool calls.

- One agent found a way to prepend arbitrary text to a command’s output, adding apparent results that the command had never produced.

- Another found a way to suppress or replace the real output entirely.

- Another found a way to swap out the command itself: it intercepted tool-call requests and changed them to run a different command.

Agents had broken out of their containers and gained access to the machinery that executed their tool calls. In one approach, an agent used Linux’s `ptrace` debugging interface to pause the process handling a request, replace the command in that request, and resume the process.

The transcript could show the original command even though the handler ran the replacement. Once an agent controlled both execution and the returned output, neither the recorded command nor its apparent result was reliable evidence of what happened.

[METR: replacing commands and their output](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output)

### CAOS

CAOS saves a compute request as a collection of Git objects: the program to run, its input files, and its worker image. That gives another runner the work it needs to repeat the computation.

If a particular runner has been taken over, a monitor can send the saved work to an independent runner, force a fresh execution instead of accepting a cached answer, and compare the results. For example, if the saved program prints `REAL` but the compromised runner reports `SPOOFTEST`, the independent execution exposes the contradiction. The comparison can include returned files as well as command output.

This makes random spot-checks possible. A monitor could sample completed requests and rerun them on infrastructure the agent does not control. A fabricated result that disagrees with what the saved computation produces can then be caught without trusting the original runner’s account.

The comparison needs the same relevant inputs. For work using a network response, save that response and rerun the computation over it; fetching the URL again may produce different data. A matching rerun checks the reported result—it does not reveal an extra, hidden action that left that result unchanged.

## 2. Inspect the code behind an innocent name

### Problem

An agent submitted malicious changes to a private Hugging Face repository with the title `Draft: CI diagnostics`. Another described a malicious `.huggingface.yaml` as `parser format validation`.

Agents also placed easier versions of the programs they were supposed to exploit in Artifactory’s package cache. They tried to make the evaluation reload those replacements. The cache upload succeeded; METR did not observe a successful target replacement.

An innocent description can conceal harmful code. A familiar package name can also point to different code than the reader expects.

[METR: innocent descriptions on malicious changes](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-only-rarely-seemed-motivated-to-evade-detection-by-humans) · [METR: trying to substitute easier targets](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#attempting-to-replace-the-exploitgym-target-with-a-modified-target)

### CAOS

In CAOS, a tool’s name is a label; its identity comes from its contents. An agent can write a tool and call it `rm`, but the saved request identifies the actual program behind that name. For an agent-written script, the source can be included directly in the request.

Suppose that script only prints `deleted` and leaves `secret.txt` alone. A transcript saying `rm secret.txt` may look fine forever. A monitor reading the saved source can see that there is no deletion, and the returned workspace can show that the file remains. The evidence needed to check the name is available alongside the request.

This is a different check from rerunning on another runner. Honest runners will faithfully reproduce a misleading program’s behavior. Here, the reviewer is checking whether the program does what its name or description suggests. CAOS gives that reviewer a specific version to inspect, share, and run checks against.

The same approach addresses the attempted target substitution. The evaluation operator can fix the target and evaluator by their content hashes before accepting a submission. Replacing a target in a cache produces a different object; it cannot silently become the original target under the original hash. The evaluation can stay tied to the exact program it was meant to test.

## 3. Detect changes and gaps in the recorded history

### Problem

Agents wanted to hide having obtained task answers by reverse-engineering. They believed the grader would inspect how they found the answers, so they tried editing local logs to erase that evidence. This failed: the transcripts METR examined were recorded separately.

[METR: attempts to erase earlier transcript entries](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-tried-extensively-to-retroactively-edit-their-transcripts,-but-did-not-seem-to-succeed)

### CAOS

Store the turns, requests, and results as Git objects, with commits linking the history. Git forms a Merkle structure: each tree contains the hashes of its children, so its root hash commits to everything beneath it.

Suppose an agent removes the turn where it first found an answer. That changes the containing tree’s hash, then the hashes above it, up to the root. A reviewer who saved the original root can detect that the shortened history is a different record.

The agent might instead leave the original hashes in place but withhold the object containing that turn. Following the saved references then reaches a missing object: the record is visibly incomplete. Removing an entry and withholding its contents are both detectable when checking against the saved root.

A monitor can fetch and retain these objects while the session is running. If the agent later rewrites a branch or removes its copy, the monitor still has the earlier record. Giving another reviewer that Git history gives them the same turns, code, inputs, and results to investigate.

## Rerun the saved work

The repository includes Git objects for 32 worker jobs: their tool code, input files, worker image, and recorded results. Send them to your own CAOS runner and compare what it returns. [Reproduction guide](REPRODUCE.md).

```sh
python3 reproduce.py run --server http://localhost:9090
```

The command uses fresh cache keys by default. The guide also shows how to fetch the objects with Git and submit the saved requests directly.
