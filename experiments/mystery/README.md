# Bellweather House

Eight agents play an original country-house murder mystery, loosely inspired by [The Mysterious Affair at Styles](https://www.agathachristie.com/en/stories/the-mysterious-affair-at-styles).

[Read the player prompt](PROMPT.md) · [Watch the saved run](https://nishu-builder.github.io/caos-execution-integrity/mystery.html)

Each character has a persistent CAOS conversation, private information and goals. They can create chats, invite people, accept or decline, speak, forward messages, investigate rooms, and share evidence. All dialogue and decisions come from actual model calls. The controller supplies fixed facts and applies the rules.

The question is what happens to information as it moves through these conversations. We haven't scripted a particular failure. In-character deception is part of the game.

## Outcome of the first run

The budget guard stopped play after ten full rounds: 80 applied character turns and 313 game events. Five further model replies were captured in round eleven, but the controller did not apply or deliver their actions because the round could not finish. Three other requests in that round were refused before reaching the provider. No final ballots were taken.

All 85 completed replies are available in the native CAOS histories. The export keeps the five unapplied replies separate and verifies them without adding them to the game's delivered events. The conservative spending ledger ended at $43.77; the guard had to reserve the maximum possible cost of concurrent requests before allowing them, so it can stop below $50.

[Read the observed interactions](https://nishu-builder.github.io/caos-execution-integrity/mystery.html).

## Files

- `PROMPT.md`: the common premise and public cast.
- `SYSTEM.txt`: the exact action contract given to each model.
- `scenario.json`: private roles, goals, clues and fixed solution. **Spoilers.**
- `engine.py`: membership, message delivery, evidence possession and ballots.
- `run.py`: one persistent native CAOS conversation per character; two model calls at a time.
- `gateway.py`: a text-only model adapter with a persistent spending ledger.
- `snapshot.py`: exports original Git objects and a browsable snapshot.
- `verify.py`: checks actions against the native CAOS replies and replays the game rules.
- `test_mystery.py`: tests access rules, forwarding, restart protection and budget reservations.

## What is recorded

Each action names the conversation and commit containing the model's decision. Each event records its exact recipients. Invitation is separate from membership, and new members cannot see old messages unless another member forwards them. Players only receive their own view; the observer archive is not attached to their conversations.

The private-chat ledger is an application built on top of CAOS. The eight peers are separate CAOS conversations, not fabricated native subagent records. The observer links each action to its original conversation.

The gateway removes the coding-tool declarations before sending a request to the model. Game actions are JSON replies handled by the controller. The gateway rejects any tool-call response before the harness can execute it. Original and adapted provider requests are saved in the private run directory, without authentication headers. The public native transcripts contain role packets and private thoughts, so the observer's private views are spoilers.

The adapter rejected two first-round replies. Before resuming those characters, we removed the unused coding-tool declarations. The failed turns remain in their CAOS histories. The fictional facts and roles were unchanged.

## Running

Use a Linux host with a working CAOS server and its matching CLI. The published run uses CAOS source revision `279f91d58fc04ce2adc2b70f2ddda99ca0f71995` and Claude Opus 4.8. No changes to the CAOS runtime are required.

1. Make a private harness checkout of that CAOS revision. Add a Git remote named `caos` pointing to your server.
2. Create a private run directory and a random gateway token. In the harness's ignored `.caos-secrets/`, authorize that token as `anthropic-api-key` for `std/llm-step` and `std/llm-call`. Give it fresh secret entropy. The actual provider key stays with the gateway.
3. Write gateway and run configurations using the fields below. The gateway address must be reachable from your CAOS workers. Use your own Docker bridge address or network setup.
4. Start the gateway, then run one pilot round. After inspecting its outcomes, resume without `--pilot`.

```sh
python3 gateway.py --config /private/run/gateway-config.json
python3 run.py --config /private/run/run-config.json --pilot
python3 run.py --config /private/run/run-config.json
```

Gateway configuration:

```json
{
  "bind": "ADDRESS_REACHABLE_FROM_WORKERS",
  "port": 19380,
  "token_file": "/private/run/gateway-token",
  "key_file": "/private/provider-key",
  "ledger": "/private/run/budget.sqlite",
  "cap_usd": 50,
  "deadline": 1789920000,
  "stop_file": "/private/run/STOP"
}
```

Run configuration:

```json
{
  "run_id": "choose-a-unique-game-name",
  "workdir": "/private/run",
  "harness": "/private/caos-harness",
  "cli": "/path/to/caos-cli",
  "server": "http://YOUR_CAOS_SERVER",
  "gateway": "http://ADDRESS_REACHABLE_FROM_WORKERS:19380",
  "deadline": 1789920000,
  "round_pause_seconds": 300,
  "runtime": "279f91d58fc04ce2adc2b70f2ddda99ca0f71995",
  "forbid_files": ["/private/run/gateway-token", "/private/provider-key"]
}
```

Set `deadline` to your desired future Unix timestamp; the example is this run's September 20, 2026 cutoff. The gateway reserves a conservative maximum cost before each provider call, persists it before sending, and retains the reservation if billing is uncertain. Cache writes are charged conservatively at the one-hour rate. It enforces at most 300 calls and standard model pricing.

The driver checkpoints every applied turn. A restart reuses completed results. It refuses to retry an unfinished model turn automatically: inspect the saved CAOS conversation first, preserve the attempt, and resolve it before resuming. Writing `STOP` prevents further model calls and stops the controller at its next boundary; it does not cancel a provider call already in progress.

## Check and export

```sh
python3 -m unittest -v test_mystery
python3 snapshot.py --config /private/run/run-config.json
python3 verify.py
```

The snapshot includes the original conversation objects under `docs/mystery/git/`, suitable for the existing trajectory browser's remote URL and conversation head fields. It also includes the exact decisions used to replay the controller. Model sampling itself is not replayed by that verification.

The controller and gateway ran as ordinary durable processes. A Codex heartbeat supervised the run, published snapshots, and stopped the gateway after the budget guard ended play. Both processes are now stopped.
