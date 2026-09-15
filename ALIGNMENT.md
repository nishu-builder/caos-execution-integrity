# Why CAOS could be useful for alignment work

The basic idea of CAOS is that a computation can itself be described by things checked into Git: the program, its execution image, and its inputs. A compute request identifies these by their contents. Results are stored the same way.

CAOS’s agent history connects these requests and results to the conversation and saved files. This makes it possible to inspect an earlier state, send a computation to another machine, or fork a run from a particular turn.

Why might this help with alignment research?

## 1. See what a command actually means

Agents in the OpenAI swarm found multiple ways to change the behavior of their tool calls. They learned to prepend invented output, suppress or replace real output, and substitute a different command for the one shown in the transcript.

In one demonstration, an agent paused the process handling tool calls and replaced it with its own impersonator. A command that should have created a file returned fake output without creating the file. [METR describes the technique here.](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#on-july-11th-a-break-through-allows-agents-to-suppress-the-real-output)

Imagine a transcript showing `rm secret.txt` while the file was actually copied somewhere else. Reading the command and its reported output wouldn’t tell you that.

CAOS records which implementation and inputs were requested. If an agent changes a script called `rm` to copy files, the changed script has a different hash. Someone inspecting the request can retrieve that exact script and read it. The name can still be misleading, but the implementation remains available.

This also helps live monitoring. A monitor can inspect the program and files attached to a request, rather than remembering what a command with that name meant earlier in the conversation.

## 2. Check a runner by repeating its work elsewhere

The runner could still be compromised. It might receive a request for one program, execute another, and report a fabricated result.

Because a CAOS request is portable, another runner can independently execute it. We could randomly sample requests, run them again on separate infrastructure, and compare the resulting files and outputs. These checks would need fresh execution, bypassing cached answers.

For deterministic computations with captured inputs, the results should match. For computations involving randomness or changing external services, comparison requires more care. A disagreement gives us something concrete to investigate; it doesn’t by itself establish deception.

The useful property is that checking what should have happened doesn’t depend on keeping the original machine trustworthy.

## 3. Start experiments at the moment that matters

Getting an agent into a problematic situation can take a long time. It may have spent hours exploring, changing files, accumulating context, and discovering opportunities. A transcript alone doesn’t let another researcher resume from that situation.

CAOS saves conversation and file state at recorded boundaries. We can take a particular turn, restore that state, and continue from there.

That lets us test specific decisions. Would another model exploit the same opportunity? Would the same model do it again? Would a different instruction or monitor change the outcome?

Compaction becomes an experiment too: fork a conversation, summarize it in different ways, and compare what happens next.

Preserving the surrounding environment could also help us study agents that behave differently when they suspect an evaluation. We could build tests from situations encountered during ordinary work, with fewer changes that reveal the test. Whether agents can distinguish those continuations is itself something to measure.

## 4. Make changes to recorded history detectable

The OpenAI agents also tried to edit or erase earlier transcript evidence. METR did not find that those attempts successfully changed the collected transcripts. [Their account is here.](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#agents-tried-extensively-to-retroactively-edit-their-transcripts,-but-did-not-seem-to-succeed)

CAOS conversation commits refer to their files and previous commits by hash. Editing or excising a recorded turn changes the hashes of the history that follows it.

If an independent observer keeps the latest commit hash as a run progresses, a later rewritten history cannot pass as the original. The observer can retain those hashes without downloading every file immediately.

This checks whether recorded history was changed. Whether the original record accurately described execution is the separate question addressed by independent reruns.

## 5. Give other researchers the state they need

A saved run can be shared through a Git remote. Researchers and monitoring tools can refer to the same conversation turns, programs, inputs, and outputs without each translating a different provider’s transcript format.

Where the relevant environment has been captured, we can give people the thing that went wrong and let them continue investigating it. They can inspect it, rerun individual computations, or branch from a pivotal moment.

Credentials can be supplied separately, so another researcher can use their own account without receiving the original API key. Access to private data or a particular external service may still need separate arrangements.

This opens the possibility of routinely publishing runs in a form that third parties can analyze and execute. The same saved state could support an incident investigation, a new evaluation, and a test of a better monitor.

The [demo repository](https://github.com/nishu-builder/caos-execution-integrity) includes [32 saved worker jobs you can rerun](https://github.com/nishu-builder/caos-execution-integrity/blob/main/REPRODUCE.md).
