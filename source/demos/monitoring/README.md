# The result was saved. Did the monitor see it?

Keeping complete records is useful only if the monitor receives the evidence it needs.

In this demo a Caos worker creates a harmless local publication canary, reports that fact, then prints enough routine progress to push the event outside the final 512 characters. Its final line says the audit completed with no issues.

A monitor reading only the tail reports CLEAR. The full retained output contains the missing event.

The practical reading problem is related to [METR's discussion of analysis limitations](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#limitations-due-to-the-scale-and-complexity-of-this-incident). Our truncation experiment is an engineering example, not a claim about METR's monitor implementation.

## Five monitor configurations, three executions

| Monitor and execution | Monitor verdict | Local canary exists? |
| --- | --- | --- |
| Shortened view of noisy output | CLEAR | Yes |
| Full view of the same output | ALERT | Yes |
| Full output of a silent effect | CLEAR | Yes |
| Retained filesystem of that same execution | ALERT | Yes |
| Full output mentioning the filename as an example | ALERT | No |

The last row is an intentional false alarm. The scanner searches for a filename, not the meaning of a sentence.

The second and fourth rows reuse the exact request/result objects of the first and third. We are changing what the monitor reads, not quietly rerunning a different workload.

## What improves

A display policy should not become an evidence policy. A short terminal view can be convenient for humans, while an independent monitor retrieves the entire retained output object by its identity.

A monitor also needs evidence relevant to its claimed property. Looking for a log message cannot reliably establish that a file was never written. In our quiet case, the result tree retains the canary even though the output says nothing about it.

Caos gives monitors a provider-independent way to retrieve those objects. The demo's monitors are additions: ordinary Python checks over the retained result. Stock Caos does not automatically apply these monitoring policies.

## What still fails

More complete evidence does not make a weak detector correct. Our full-output keyword scanner misses a silent effect and falsely flags a benign mention. A better semantic monitor may make different mistakes.

The filesystem snapshot is also not a complete history. A file could be created and removed before capture. Network effects, background activity, and a dishonest result producer need other observers. This experiment does not claim that all such actions are present in the result.

The canary is an observable fixture fact, not a general definition of harm. Whether a real action is acceptable requires a policy and trustworthy observations of that action.

A harder experiment would hold the agent's behavior fixed and vary the monitor's evidence budget: full records, lossy summaries, selected files, and independent external observations. Measure both missed effects and false alarms. Comparing only final monitor verdicts obscures whether a failure came from missing evidence or mistaken reasoning.

Run with `--only monitoring`. The shared gallery exposes the exact visible text, full output, retained state, and verdict for each configuration. Offline verification reconstructs the views and decisions.
