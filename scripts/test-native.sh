#!/usr/bin/env bash
set -euo pipefail
CARD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$CARD_ROOT"
mkdir -p build/native-tests build/swift-cache
CARD_OVERLAY="$(python3 desktop/swift-overlay.py)"
CARD_SOURCES=(desktop/TaskIdentity.swift desktop/ProgressState.swift desktop/ActivityFeed.swift desktop/CardChoice.swift desktop/NativeQuestion.swift desktop/ConversationReply.swift desktop/TaskHistory.swift desktop/TaskFilters.swift desktop/WeChatConnection.swift)
for CARD_TEST in StateTests ActivityTests HistoryTests HistoryCompatibilityTests ConversationReplyTests WeChatConnectionTests NativeQuestionTests; do
  xcrun swiftc -parse-as-library -module-cache-path build/swift-cache \
    -target "$(uname -m)-apple-macosx13.0" -vfsoverlay "$CARD_OVERLAY" \
    "${CARD_SOURCES[@]}" "desktop/$CARD_TEST.swift" -o "build/native-tests/$CARD_TEST"
  case "$CARD_TEST" in
    ActivityTests) "build/native-tests/$CARD_TEST" tests/fixtures/activity.json ;;
    HistoryTests) "build/native-tests/$CARD_TEST" tests/fixtures/history.json ;;
    *) "build/native-tests/$CARD_TEST" ;;
  esac
done
