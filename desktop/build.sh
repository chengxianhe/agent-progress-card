#!/bin/bash
set -euo pipefail
CARD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CARD_APP="${WEIGUANG_APP_OUTPUT:-$CARD_ROOT/build/微光.app}"
CARD_ARCH="${WEIGUANG_ARCH:-$(uname -m)}"
case "$CARD_ARCH" in arm64|x86_64) ;; *) echo "Unsupported Mac architecture" >&2; exit 1 ;; esac
CARD_IDENTITY="${WEIGUANG_SIGN_IDENTITY:--}"
mkdir -p "$CARD_APP/Contents/MacOS" "$CARD_APP/Contents/Resources" "$CARD_ROOT/build/swift-cache"
CARD_OVERLAY="$(python3 "$CARD_ROOT/desktop/swift-overlay.py")"
xcrun swiftc -parse-as-library -O -module-cache-path "$CARD_ROOT/build/swift-cache" \
  -target "$CARD_ARCH-apple-macosx13.0" \
  -vfsoverlay "$CARD_OVERLAY" \
  "$CARD_ROOT/desktop/TaskIdentity.swift" "$CARD_ROOT/desktop/ProgressState.swift" "$CARD_ROOT/desktop/CardWindow.swift" \
  "$CARD_ROOT/desktop/ActivityFeed.swift" "$CARD_ROOT/desktop/ActivityModel.swift" \
  "$CARD_ROOT/desktop/NativeQuestion.swift" "$CARD_ROOT/desktop/NativeQuestionView.swift" \
  "$CARD_ROOT/desktop/ChatField.swift" "$CARD_ROOT/desktop/ChoiceFormView.swift" "$CARD_ROOT/desktop/CardChoice.swift" "$CARD_ROOT/desktop/ChoicePromptView.swift" \
  "$CARD_ROOT/desktop/ConversationReply.swift" "$CARD_ROOT/desktop/ConversationReplyView.swift" \
  "$CARD_ROOT/desktop/ToolActivityView.swift" \
  "$CARD_ROOT/desktop/WorkExplanationView.swift" \
  "$CARD_ROOT/desktop/TaskHistory.swift" "$CARD_ROOT/desktop/TaskFilters.swift" "$CARD_ROOT/desktop/TaskDashboard.swift" \
  "$CARD_ROOT/desktop/WeChatConnection.swift" \
  "$CARD_ROOT/desktop/GlimmerTheme.swift" "$CARD_ROOT/desktop/CardView.swift" \
  "$CARD_ROOT/desktop/GlimmerTitlebarAccessory.swift" \
  "$CARD_ROOT/desktop/CardPaths.swift" "$CARD_ROOT/desktop/BundledPython.swift" \
  "$CARD_ROOT/desktop/SetupWorker.swift" "$CARD_ROOT/desktop/FirstRunModel.swift" \
  "$CARD_ROOT/desktop/FirstRunView.swift" "$CARD_ROOT/desktop/ProgressInstructions.swift" \
  "$CARD_ROOT/desktop/WeChatSetupModel.swift" "$CARD_ROOT/desktop/WeChatSetupView.swift" \
  "$CARD_ROOT/desktop/AgentProgressCard.swift" \
  -o "$CARD_APP/Contents/MacOS/AgentProgressCard"
mkdir -p "$CARD_APP/Contents/Resources/agent_progress_card" "$CARD_APP/Contents/Resources/agent_progress_wechat"
cp "$CARD_ROOT"/src/agent_progress_card/*.py "$CARD_APP/Contents/Resources/agent_progress_card/"
cp "$CARD_ROOT"/src/agent_progress_wechat/*.py "$CARD_APP/Contents/Resources/agent_progress_wechat/"
bash "$CARD_ROOT/desktop/build-icon.sh" "$CARD_APP/Contents/Resources"
CARD_PYTHON="$(python3 "$CARD_ROOT/desktop/prepare-runtime.py" --arch "$CARD_ARCH")"
mkdir -p "$CARD_APP/Contents/Resources/Python"
python3 "$CARD_ROOT/desktop/assemble-runtime.py" "$CARD_PYTHON" "$CARD_APP/Contents/Resources/Python"
cp "$CARD_ROOT/desktop/worker.py" "$CARD_APP/Contents/Resources/worker.py"
/usr/bin/ditto "$CARD_ROOT/desktop/runtime/licenses" "$CARD_APP/Contents/Resources/Python/licenses"
cp "$CARD_ROOT/desktop/runtime/license-source.json" "$CARD_APP/Contents/Resources/python-license-source.json"
cp "$CARD_ROOT/desktop/runtime/python-lock.json" "$CARD_APP/Contents/Resources/python-runtime-source.json"
cp "$CARD_ROOT/LICENSE" "$CARD_ROOT/NOTICE" "$CARD_ROOT/THIRD_PARTY_NOTICES.md" "$CARD_APP/Contents/Resources/"
xcrun clang -O2 -Wall -Wextra -Werror -target "$CARD_ARCH-apple-macosx13.0" \
  "$CARD_ROOT/desktop/cli-launcher.c" -o "$CARD_APP/Contents/MacOS/weiguang-cli"
python3 "$CARD_ROOT/desktop/write-info.py" --app "$CARD_APP" --arch "$CARD_ARCH" --identity "$CARD_IDENTITY"
python3 "$CARD_ROOT/desktop/sign-app.py" --app "$CARD_APP" --identity "$CARD_IDENTITY"
printf '%s\n' "$CARD_APP"
