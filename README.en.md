# Agent Progress Card

[中文](README.md)

A native macOS card showing an AI assistant's task status, public work notes, tool calls,
latest reply and task history. An optional owner-only WeChat relay sends tasks to an already-open,
explicitly bound Codex conversation and supports one-time command approvals from a phone.

No web server or additional model API key is required. This is not an agent engine: work stays in
Codex. It does not expose hidden reasoning or read unrelated conversations, personal chats or groups.

## Features

- Draggable, pinnable SwiftUI/AppKit card with expanded and compact views.
- Current/history selection, task categories and tool/failure filters.
- Redacted, bounded tool details and public work notes; latest completion reply.
- Average output tokens per second for the current turn, including tool wait time.
- Explicit numbered card choices, separate read-only native question notices, and optional command approvals.
- Owner-only WeChat pairing, queued notifications, retry/backoff and delivery status.
- Optional per-user background supervision that restarts failed relays and respects manual stops.

## Build and install

Requires macOS 13+, Xcode Command Line Tools and Python 3.10+.
The bundled collector uses CLT's `/usr/bin/python3`; that subset supports Python 3.9.

```bash
git clone https://github.com/chengxianhe/agent-progress-card.git
cd agent-progress-card
bash desktop/build.sh
open build/AgentProgressCard.app
```

Install missing build tools with `xcode-select --install`. Builds target your machine's architecture
and are ad-hoc signed, not notarized. The local module-map overlay does not modify the system SDK.

Optionally run `python3 desktop/install.py` to install under `~/Applications/`.
It refuses to overwrite an existing app; read [migration instructions](docs/migration.md) before updating.
Closing the window hides it; Cmd+Q exits the app and its event collector. WeChat services are separate.

## Attach a conversation and publish progress

Use an explicitly selected transcript and its matching thread UUID:

```bash
PYTHONPATH=src python3 -m agent_progress_card.attach \
  --transcript /absolute/path/to/rollout.jsonl --thread-id THREAD_UUID
```

Attachment validates the identity and reads public events from the recent turn onward.
Do not scan unrelated conversations to guess a binding. The app must remain open for its collector;
the WeChat supervisor does not replace it.

Progress can also be published explicitly:

```bash
PYTHONPATH=src python3 -m agent_progress_card begin --title 'Review docs' --action 'Read source'
# Replace TASK_ID with the returned ID.
PYTHONPATH=src python3 -m agent_progress_card update --task-id TASK_ID \
  --status succeeded --action 'Automatic checks passed'
```

States are `running`, `waiting`, `succeeded` and `failed`. Use `waiting` for human review.
A final reply or succeeded state is not user acceptance. `begin --replace` changes the displayed task,
not the assistant's running work. Output token rate is an average, not instantaneous speed or cost.

## Owner-only WeChat relay

Open the bound conversation in Codex, then run:

```bash
PYTHONPATH=src python3 -m agent_progress_wechat.relay \
  --state-dir "$PWD/runs/wechat" --thread-id THREAD_UUID
```

Pair in the card's connection settings. Your account must support iLink/ClawBot; availability depends
on the service. Only the pairing owner is accepted. See [WeChat details](docs/wechat.md).

Ordinary text enters the same Codex conversation and incurs normal model usage. Local commands
`进度` (progress), `结果` (result), `帮助` (help), `选项` (choices) and `审批` (approvals) query local state.
Polling and local state queries do not call the model. Use the card's stop button to pause synchronization.

### Three different kinds of choices

| Type | How it is answered |
| --- | --- |
| Explicit card choice | Card click or WeChat number becomes a user message in the bound conversation |
| Native ordinary form | Mirrored as a read-only notice; answer in the original client |
| Command approval | Opt-in formal approval response, sent only after the owner explicitly chooses |

Publish an ordinary card choice:

```bash
PYTHONPATH=src python3 -m agent_progress_card choice \
  --question 'Which part first?' --option 'Card UI' --option 'WeChat relay'
```

Acknowledged delivery clears the choice. Ambiguous delivery is not automatically resubmitted.
If the user answers directly in chat or cancels, call
`PYTHONPATH=src python3 -m agent_progress_card clear-choice`. Choices expire after 24 hours.

### One-time command approvals

Stop the existing relay normally, then restart with `--remote-approvals` to opt in.
This preference is retained for the paired account and thread. Restart with `--no-remote-approvals`
to disable it. Codex permissions, model settings and persistent command rules are not overridden.

WeChat preserves the server-provided option order. Reply with an option number and the displayed
approval code, separated by a space. A bare number works only for one notified pending approval
with no competing ordinary choice. Never assume that a fixed number always means approval.

Compact prompts show the command, working directory, reason and numbered options.
Command previews are limited to 1,400 characters (directory: 300; reason: 400).
Fallback notices explain why desktop confirmation is needed without echoing sensitive content.
Long-command approval on the phone is not yet supported. Codes expire within 10 minutes and become
invalid after disconnection, restart or desktop resolution. One-time allow, decline and cancel are supported;
options granting session-wide or persistent permission remain desktop-only. Unsupported or incomplete
permission previews also stay in the original client. A request-closed receipt is not proof of command success.
See [approval implementation and validation](docs/remote-approvals.md).

### Background operation and missing replies

An explicitly installed per-user LaunchAgent starts after login and supervises the relay.
It avoids duplicate pollers and respects manual stop requests. See [setup and removal](docs/wechat-resident.md).

Supervision cannot remove WeChat's upstream delivery restrictions. `-2 / prepare failed` may mean that
outbound replies are temporarily rejected while the local process still receives messages; it does not by
itself establish login expiry. Notifications stay queued and retry with backoff up to five minutes.
Send `进度` or `选项` to refresh the reply context; re-pair only when login is reported as expired.
Server acceptance does not prove the phone displayed a message. Sleep, network loss and a closed Codex
conversation also affect operation.

## Privacy, compatibility and verification

State lives under `~/Library/Application Support/AgentProgressCard/`; WeChat credentials and queues
live in the chosen state directory. Credentials, raw chats, real session identifiers, databases, QR codes,
logs and build output are excluded from source publication. Redaction remains best effort.
History is bounded to 12 tasks, 20 calls and 30 work notes per task; it is not a complete audit archive.

Local Codex integration is experimental, tested with CLI 0.167.0. Revalidate after client upgrades.

```bash
bash scripts/verify.sh
```

Currently runs 131 Python tests, both native builds and seven native model suites on macOS.
Tests use synthetic data and do not contact WeChat. Live messaging, mobile approvals and window interaction
require separate validation. Logs stay in ignored `build/verification/`; see [verification scope](docs/verification.md).

Sources: `desktop/` for native UI/build tools, `src/agent_progress_card/` for state and collection,
`src/agent_progress_wechat/` for the relay, and `tests/` for regression tests.
This repository has its own package names and history, with no dependency on the original demo engine.
[MIT License](LICENSE); retained attribution is in [NOTICE](NOTICE).
