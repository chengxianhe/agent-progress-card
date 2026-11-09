# Agent Progress Card

[中文](README.md)

A standalone native macOS card for observing an AI assistant's task status, public work notes,
tool calls, latest reply and task history. An optional owner-only WeChat relay sends text to an
explicitly bound, already-open Codex session and returns public progress.

The card is not an agent engine. It needs no web server or model API key. It does not expose hidden
reasoning, approve tool permissions or read unrelated conversations.

## Build

Requires macOS 13+, Xcode Command Line Tools and Python 3.10+. The bundled watcher uses
`/usr/bin/python3` supplied with CLT; the watcher subset remains compatible with Python 3.9.

```bash
git clone https://github.com/chengxianhe/agent-progress-card.git
cd agent-progress-card
bash desktop/build.sh
open build/AgentProgressCard.app
```

The build is native to your machine and ad-hoc signed, not notarized. Optional installation:
`python3 desktop/install.py`. This refuses to overwrite an existing app. See [migration](docs/migration.md).

## Publish progress and attach a session

```bash
PYTHONPATH=src python3 -m agent_progress_card begin --title 'Review docs' --action 'Read source'
# Replace TASK_ID with the returned ID.
PYTHONPATH=src python3 -m agent_progress_card update --task-id TASK_ID \
  --status succeeded --action 'Checks passed'
PYTHONPATH=src python3 -m agent_progress_card.attach \
  --transcript /absolute/path/to/rollout.jsonl --thread-id THREAD_UUID
```

Use `waiting` for pending human review. Opening the card alone does not publish tasks or discover
sessions. Attachment validates the specified transcript and thread. The app starts the reader and
stops it on exit. Public notes, final replies and tool summaries are filtered, bounded and redacted.

The UI supports pinning, expansion, current/history selection and overview/process/tools/results
categories. A final reply is separate from task acceptance. State remains in
`~/Library/Application Support/AgentProgressCard/` for compatibility.

## Optional WeChat relay

Keep the card and the matching Codex session open, then run:

```bash
PYTHONPATH=src python3 -m agent_progress_wechat.relay \
  --state-dir "$PWD/runs/wechat" --thread-id THREAD_UUID
```

Pair through the card's connection settings. Your WeChat account must support the corresponding
iLink/ClawBot connection. Only the pairing owner is accepted. It does not access ordinary chats,
groups or the WeChat database. See [WeChat details](docs/wechat.md).

The relay inherits the existing session's permissions and never approves requests on your behalf.
Ordinary text sent to the session incurs normal model usage; polling and local status queries do not.
Sleep, network loss or stopping the relay interrupts delivery. There is no background startup service.
Local Codex integration is experimental, historically verified against CLI 0.167.0, not a stable API.

## Verify

```bash
bash scripts/verify.sh
```

Runs standard-library Python tests and, on macOS, both Swift builds plus six native model suites.
Logs go to ignored `build/verification/`. Tests use synthetic data and do not contact WeChat.
Desktop interaction and real pairing require separate validation.

Runtime credentials, databases, transcripts and build output are never part of the source distribution.
Redaction is best effort. Source lives in `desktop/`, `src/agent_progress_card/` and
`src/agent_progress_wechat/`. This repository has its own history and no dependency on the original
demo engine. [MIT License](LICENSE); retained attribution is in [NOTICE](NOTICE).
