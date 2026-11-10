import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_progress_card.activity import ActivityReader
from agent_progress_card.choice import create_choice, read_choice
from agent_progress_card.watcher import atomic_json
from agent_progress_wechat.relay_mirror import choice_text, mirror
from agent_progress_wechat.relay_store import RelayStore
from agent_progress_wechat.relay_service import selected_message
from agent_progress_wechat.card_choice import process_card_choice
import json


class UsageRateTests(unittest.TestCase):
    def test_turn_rate_uses_output_delta_not_session_total(self):
        reader = ActivityReader("thread", 0)

        def event(second, kind, **extra):
            return {"type": "event_msg", "timestamp": datetime.fromtimestamp(second, timezone.utc).isoformat(),
                    "payload": {"type": kind, **extra}}

        reader.consume(event(100, "task_started"))
        reader.consume(event(110, "token_count", info={"total_token_usage": {"output_tokens": 1000},
                                                       "last_token_usage": {"output_tokens": 100}}))
        self.assertEqual(reader.snapshot(111)["output_rate"], 10.0)
        reader.consume(event(120, "token_count", info={"total_token_usage": {"output_tokens": 1100},
                                                       "last_token_usage": {"output_tokens": 100}}))
        self.assertEqual(reader.snapshot(121)["output_rate"], 10.0)
        reader.consume(event(125, "task_started"))
        self.assertIsNone(reader.snapshot(126)["output_rate"])


class ChoiceTests(unittest.TestCase):
    def test_card_selection_sends_once_to_bound_thread_without_wechat_context(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_json(root / "activity-source.json", {"thread_id": "thread"})
            choice = create_choice(root, "哪项？", ["甲", "乙"])
            atomic_json(root / "choice-selection.json", {"choice_id": choice["id"], "thread_id": "other", "index": 2})

            class Connection:
                calls = []

                def call(self, method, params):
                    self.calls.append((method, params))
                    return {"turn": {"id": "turn"}}

                def close(self):
                    pass

            class Session:
                thread_id = "thread"
                connection = Connection()

                def open(self):
                    return self.connection

                def prepare(self, connection, text, identity, source):
                    self.connection.calls.append(("prepare", (text, identity, source)))
                    return "turn/start", {"input": text}

            session = Session()
            process_card_choice(root, session)
            self.assertEqual(session.connection.calls, [])
            atomic_json(root / "choice-selection.json", {"choice_id": choice["id"], "thread_id": "thread", "index": 2})
            process_card_choice(root, session)
            process_card_choice(root, session)
            self.assertEqual(len(session.connection.calls), 2)
            self.assertEqual(session.connection.calls[0], ("prepare", ("我选择第 2 项：乙", choice["id"], "card")))
            result = json.loads((root / "choice-result.json").read_text())
            self.assertEqual(result["status"], "sent")
            self.assertEqual(result["index"], 2)
            self.assertIsNone(read_choice(root, "thread"))

    def test_bound_choice_is_deduplicated_and_numbered(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_json(root / "activity-source.json", {"thread_id": "thread"})
            choice = create_choice(root, "用哪个方案？", ["先上线", "再测试"])
            with self.assertRaises(ValueError):
                create_choice(root, "另一个问题？", ["甲", "乙"])
            self.assertIsNone(read_choice(root, "other"))
            self.assertEqual(read_choice(root, "thread"), choice)
            self.assertIn("2. 再测试", choice_text(choice))
            self.assertEqual(selected_message("2", choice), "我选择第 2 项：再测试")
            self.assertEqual(selected_message("3", choice), "3")
            self.assertEqual(selected_message("2", None), "2")
            store = RelayStore(root / "wechat", "owner", "thread")
            state = {"task_id": "task", "title": "示例", "status": "waiting", "action": "选择", "detail": ""}
            feed = {"thread_id": "thread", "notes": [], "pending": [], "choice": choice}
            mirror(store, state, feed)
            mirror(store, state, feed)
            count = store.db.execute("SELECT count(*) FROM outbox WHERE id=?", ("choice:" + choice["id"],)).fetchone()[0]
            self.assertEqual(count, 1)
            self.assertIsNone(store.outgoing())
            store.put("context", "fake-context")
            store.put("context_at", __import__("time").time())
            self.assertEqual(store.outgoing()["id"], "choice:" + choice["id"])
            feed["choice"] = None
            mirror(store, state, feed)
            self.assertIsNone(store.db.execute("SELECT id FROM outbox WHERE id=?", ("choice:" + choice["id"],)).fetchone())
            store.db.close()

    def test_invalid_or_stale_choice_is_not_shown(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atomic_json(root / "activity-source.json", {"thread_id": "thread"})
            with self.assertRaises(ValueError):
                create_choice(root, "question", ["one"])
            choice = create_choice(root, "question", ["one", "two"])
            choice["created_at"] = 1
            atomic_json(root / "choice.json", choice)
            self.assertIsNone(read_choice(root, "thread"))
