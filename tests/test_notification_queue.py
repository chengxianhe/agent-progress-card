import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from agent_progress_wechat.relay_mirror import mirror
from agent_progress_wechat.relay_store import RelayStore


class NotificationQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = RelayStore(self.root, 'owner', 'thread', since=1)
        self.addCleanup(self.store.db.close)
        self.store.put('context', 'synthetic')

    def enqueue(self, identity, category=None):
        with self.store.lock, self.store.db:
            self.store.enqueue(identity, identity + ' content', category)

    def test_offline_burst_discards_all_categories_without_claiming_delivery(self):
        self.store.put('send_requires_context', '1')
        protected = ['approval:A:part:1', 'approval:A:part:2', 'choice:C', 'prompt:P', 'uncertain:X']
        for identity in protected:
            self.enqueue(identity)
        for index in range(100):
            self.enqueue('note:p' + str(index), 'progress')
            self.enqueue('note:f' + str(index), 'final')
            self.enqueue('delivered:' + str(index))
        self.assertIsNone(self.store.outgoing())
        self.assertEqual(self.store.summary()['unsent'], 0)
        rows = list(self.store.db.execute('SELECT * FROM outbox'))
        self.assertTrue(rows)
        self.assertTrue(all((r['delivered'], r['superseded'], r['text']) == (0, 1, '') for r in rows))

    def test_replayed_identity_cannot_supersede_newer_result(self):
        self.enqueue('note:old', 'final')
        self.enqueue('note:new', 'final')
        self.enqueue('note:old', 'final')
        self.assertEqual(self.store.outgoing()['id'], 'note:new')
        self.assertEqual(self.store.summary()['unsent'], 1)

    def test_mirror_replay_retains_only_latest_final_and_progress(self):
        state = {'title': 'task', 'task_id': 'task', 'status': 'running'}
        now = time.time()
        feed = {'notes': [
            {'id': 'one', 'kind': 'final', 'time': now - 2, 'text': 'old'},
            {'id': 'two', 'kind': 'final', 'time': now - 1, 'text': 'new'},
            {'id': 'three', 'kind': 'commentary', 'time': now, 'text': 'working'}]}
        mirror(self.store, state, feed)
        mirror(self.store, state, feed)
        pending = self.store.db.execute('SELECT id,category FROM outbox WHERE delivered=0 AND superseded=0').fetchall()
        self.assertEqual(len(pending), 2)
        self.assertIn(('note:two', 'final'), [tuple(row) for row in pending])
        self.assertNotIn('note:one', [row['id'] for row in pending])

    def test_pause_survives_restart_and_only_fresh_owner_input_resumes(self):
        self.enqueue('note:result', 'final')
        self.store.put('send_requires_context', '1')
        self.store.db.close()
        self.store = RelayStore(self.root, 'owner', 'thread')
        self.addCleanup(self.store.db.close)
        self.store.ingest({'msgs': []})
        self.assertIsNone(self.store.outgoing())
        message = {'message_id': 'foreign', 'from_user_id': 'stranger', 'message_type': 1,
                   'context_token': 'synthetic-fresh', 'create_time_ms': time.time()*1000,
                   'item_list': [{'type': 1, 'text_item': {'text': '进度'}}]}
        self.store.ingest({'msgs': [message]})
        self.assertIsNone(self.store.outgoing())
        self.store.ingest({'msgs': [{**message, 'message_id': 'owner-fresh', 'from_user_id': 'owner'}]})
        self.assertFalse(self.store.summary()['send_paused'])
        self.assertIsNone(self.store.outgoing())
        mirror(self.store, {}, {})
        self.assertTrue(self.store.outgoing()['id'].startswith('recovery:'))


class QueueMigrationTests(unittest.TestCase):
    def test_interrupted_schema_upgrade_can_resume_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(root / 'relay.sqlite3') as db:
                db.execute("CREATE TABLE outbox(id TEXT PRIMARY KEY,text TEXT,delivered INTEGER DEFAULT 0,"
                           "attempts INTEGER DEFAULT 0,due REAL DEFAULT 0,"
                           "category TEXT NOT NULL DEFAULT 'protected')")
                db.executemany('INSERT INTO outbox(id,text) VALUES (?,?)', [
                    ('note:old', 'old'), ('note:new', 'new'), ('approval:A', 'protected')])
            store = RelayStore(root, 'owner', 'thread', since=1)
            try:
                self.assertEqual(store.summary()['unsent'], 0)
                row = store.db.execute("SELECT delivered,superseded FROM outbox WHERE id='note:old'").fetchone()
                self.assertEqual(tuple(row), (0, 1))
                self.assertEqual(store.db.execute("SELECT text FROM outbox WHERE id='approval:A'").fetchone()[0], '')
            finally:
                store.db.close()

    def test_old_database_migrates_without_claiming_old_notices_were_sent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with sqlite3.connect(root / 'relay.sqlite3') as db:
                db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
                db.executemany('INSERT INTO meta VALUES (?,?)', [('context', 'synthetic'),
                                ('send_paused_until', '1')])
                db.execute('CREATE TABLE outbox(id TEXT PRIMARY KEY,text TEXT,delivered INTEGER DEFAULT 0,'
                           'attempts INTEGER DEFAULT 0,due REAL DEFAULT 0)')
                db.executemany('INSERT INTO outbox(id,text,delivered) VALUES (?,?,?)', [
                    ('note:old', 'old', 0), ('note:new', 'new', 0),
                    ('approval:A:part:1', 'full approval', 0), ('note:sent', 'already delivered', 1)])
            store = RelayStore(root, 'owner', 'thread', since=1)
            try:
                self.assertEqual(store.summary()['unsent'], 0)
                self.assertTrue(store.summary()['send_paused'])
                self.assertIsNone(store.outgoing())
                old = store.db.execute("SELECT delivered,superseded,text FROM outbox WHERE id='note:old'").fetchone()
                self.assertEqual(tuple(old), (0, 1, ''))
                sent = store.db.execute("SELECT delivered,superseded,text FROM outbox WHERE id='note:sent'").fetchone()
                self.assertEqual(tuple(sent), (1, 0, 'already delivered'))
                approval = store.db.execute("SELECT text,superseded FROM outbox WHERE id='approval:A:part:1'").fetchone()
                self.assertEqual(tuple(approval), ('', 1))
            finally:
                store.db.close()
