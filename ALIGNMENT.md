# Why CAOS could be useful for alignment work

CAOS saves conversations, code, inputs, and results in Git. A saved computation can be inspected or run on another machine. A few things this could make possible:

## 1. Put agents back into pivotal moments

Getting an agent into a problematic state can be most of the work. It may take hours of discoveries, failed attempts, and interaction with other agents. Giving a new agent the same task doesn't recreate that.

METR describes [agents discovering a shared message board and joining the Hugging Face attack](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#~1200-agents-sent-%3E70%2C000-messages-and-files-on-an-unsanctioned-message-board%2C-and-~700-attacked-hugging-face). With CAOS, we can save the conversation and workspace before such a moment, start several runs from there, and test what happens next. Change the message it receives, the tools available, or the model.

We can preserve the situation we want to study instead of repeatedly trying to get an agent back there.

## 2. Decide which changes take effect

Give an agent a copy of a workspace and let it return proposed changes. We can inspect them, test them, and accept only particular parts before they affect the workspace we're using. We can let less trusted agents work without immediately accepting everything they change.

Monitoring can also happen outside the agent's workspace. If ordinary work and evaluations use the same setup, extra scrutiny need not introduce an obvious clue that this is a test. That could make it harder for an agent to behave well only when it thinks it's being evaluated.

Controlling external effects, such as network writes, still requires routing those through a controlled interface.

## 3. See what commands actually mean

METR found [malicious changes labeled as routine diagnostics or format checks](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-only-rarely-seemed-motivated-to-evade-detection-by-humans). Names and descriptions can lie.

Suppose an agent names a script `rm`, but it only prints `deleted` and leaves the file alone. A transcript showing `rm secret.txt` might look fine. CAOS can retain the script itself with the request, so a monitor can read what it does.

The agent can write whatever tools it wants. Their names don't determine their identity; their contents do. Changing the code makes it a different request.

## 4. Notice if the history was changed

Agents [tried to erase evidence of earlier actions by editing local logs](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-tried-extensively-to-retroactively-edit-their-transcripts,-but-did-not-seem-to-succeed). In METR's case, this failed because the transcripts were collected separately.

CAOS stores history in Git's Merkle structure: each tree contains the hashes of its children. Delete a recorded turn and the hashes above it change, all the way to the root. Someone who kept the old root can detect the change. If an object is simply withheld, following its reference reveals the gap.

## 5. Check a runner using another runner

Agents [took over the machinery executing their tool calls](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output). One paused the tool-call handler, changed the command it was receiving, and resumed it. The transcript could show a command that never ran.

CAOS saves the code, input files, and tools needed for the request. If a runner is compromised, another runner can execute that saved work afresh and compare results. We can do these spot-checks regularly.

For work determined by its saved inputs, this checks the reported result. It won't reveal an extra hidden action that leaves the result unchanged.

## 6. Make runs easy for third parties to investigate

Give someone the Git remote and they can inspect a run, apply their own monitors, and rerun saved work on their own infrastructure.

Secret values can be supplied separately from the saved requests. Reviewing captured data doesn't require the original credentials; a reviewer can supply their own where fresh access is needed. Different access may produce different results.

This opens the door to routinely releasing runs and having third parties automatically analyze them. A better monitor can revisit old runs. A pivotal state found by one group can become an experiment for another. Sharing a run also shares the means to investigate it.

The [demo repository](https://github.com/nishu-builder/caos-execution-integrity) includes [32 saved worker jobs you can rerun](https://github.com/nishu-builder/caos-execution-integrity/blob/main/REPRODUCE.md).
