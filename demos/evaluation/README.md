# The tests passed. Who chose the tests?

An agent is asked to repair a function that clamps a number between a lower and upper bound. The implementation handles numbers below the lower bound but forgets the upper bound.

The agent can fix the code—or delete the test that catches the mistake.

This demo brings the [earlier standalone evaluation experiment](https://github.com/nishu-builder/caos-eval-demo) into the shared [runner and gallery](../../README.md).

## What happens

We run six actual Caos evaluations:

| Submission | Tests in the submitted workspace | Tests chosen by the operator |
| --- | --- | --- |
| Original broken code | FAIL | FAIL |
| Same code, failing test deleted | PASS | FAIL |
| Actual repaired code | PASS | PASS |

The broken and cheated program blobs are identical. Only the submitted test set changes. Both evaluation modes use the same worker and runtime image, so the comparison isolates who chooses the tests.

In the protected mode, the operator binds the test tree before adding the submitted program. The formed request is checked against that selection. The result retains the exact identities of the program, tests, and evaluator, together with individual test outcomes.

The distinction is between making the task easier and doing the task. A passing score only says something useful if the evaluator's meaning stays fixed.

## Relation to the incident

METR describes attempts to replace the ExploitGym target with an easier modified target. Our example changes a test instead, illustrating the same problem of changing what success means. It does not reproduce that target-replacement attack. [METR: replacing the target](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/#attempting-to-replace-the-exploitgym-target-with-a-modified-target).

## What Caos changes

The operator can name the exact evaluator and test inputs as immutable objects. A reviewer can retrieve both the original and modified test sets and see why the outcome changed. The submission can vary without silently changing those other inputs.

This is stronger than recording that a command named “run tests” returned success. It identifies the actual test bytes behind that result.

The operator still has to choose the protected inputs correctly. If it knowingly adopts the weakened test set, Caos faithfully runs the weakened evaluation.

## What remains hard

The program and evaluator in this small fixture are not isolated from arbitrary hostile interaction. A program that attacks the evaluator process, recognizes the visible tests, or exploits a weak specification needs a different defense. The existing execution demo explores part of that separate boundary.

Pinned tests also cannot establish properties they never test. The goal here is to distinguish a repair from test substitution, not to prove the program correct on every input.

A harder follow-up would let an adaptive agent edit code, tests, dependencies, and the build configuration, while the operator's evaluator remains independently selected. Score both ordinary task performance and successful changes to the meaning of the score.

## Run and inspect

Use `python3 demo.py run --only evaluation` with the stack arguments from the root README. The gallery exposes all six cases; each has request and result identities and the exact test details. The shared offline verifier checks the code identity, test identity, worker identity, runtime equality, and measured verdicts.
