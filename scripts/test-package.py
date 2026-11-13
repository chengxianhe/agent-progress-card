"""Exercise a relocated app with synthetic state and deliberately hostile Python env."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
import uuid


def verify(app):
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    forbidden = {'credentials.json', 'auth.json', 'activity-source.json', 'wechat-source.json', 'state.json'}
    for path in app.rglob('*'):
        if path.name in forbidden or path.suffix == '.jsonl':
            raise AssertionError('Local state must not be present in the app')
    with tempfile.TemporaryDirectory(prefix='微光 relocation ') as temporary:
        root = Path(temporary)
        moved = root / "space and quote's 微光.app"
        subprocess.run(['/usr/bin/ditto', str(app), str(moved)], check=True)
        subprocess.run(['codesign', '--verify', '--deep', '--strict', str(moved)], check=True)
        contents = moved / 'Contents'
        python = contents / 'Resources/Python/bin/python3'
        cli = contents / 'MacOS/weiguang-cli'
        env = {**os.environ, 'PATH': '/usr/bin:/bin', 'PYTHONPATH': '/missing-python-path',
               'PYTHONHOME': '/missing-python-home', 'WEIGUANG_STATE_DIR': str(root / 'private state')}
        def run(args, valid=True):
            result = subprocess.run(list(map(str, args)), env=env, capture_output=True, text=True, timeout=20)
            if (result.returncode == 0) != valid:
                raise AssertionError(result.stderr or result.stdout)
            return result.stdout
        text = run([python, '-I', '-B', '-c',
                    'import ssl, sqlite3, json, hashlib, sys; '
                    'assert "/Resources/Python" in sys.prefix; '
                    'assert sqlite3.connect(":memory:").execute("select 2+2").fetchone()[0] == 4; '
                    'print(sys.version.split()[0], ssl.OPENSSL_VERSION)'])
        thread = str(uuid.uuid4())
        transcript = root / 'selected synthetic.jsonl'
        transcript.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': thread}}) + '\n' +
                              json.dumps({'type': 'event_msg', 'timestamp': datetime.now(timezone.utc).isoformat(),
                                          'payload': {'type': 'task_started'}}) + '\n')
        inspected = json.loads(run([cli, '--setup', 'inspect', '--transcript', transcript]))
        assert inspected['value']['thread_id'] == thread
        command = [cli, '--setup', 'connect', '--transcript', transcript, '--thread-id', thread, '--title', '合成安装任务']
        task = json.loads(run(command))['value']['task_id']
        assert json.loads(run(command, valid=False))['ok'] is False
        updated = json.loads(run([cli, 'update', '--task-id', task, '--status', 'waiting', '--action', '等待人工确认']))
        assert updated['status'] == 'waiting'
        run([python, '-I', '-B', contents / 'Resources/worker.py', 'agent_progress_card.watcher', '--once'])
        state = root / 'private state'
        assert json.loads((state / 'activity.json').read_text())['thread_id'] == thread
        assert json.loads((state / 'history.json').read_text())['tasks'][-1]['task_id'] == task
        run([python, '-I', '-B', contents / 'Resources/worker.py', 'os'], valid=False)
        assert (contents / 'Resources/Python/lib/python3.12/LICENSE.txt').is_file()
        assert len(list((contents / 'Resources/Python/licenses').glob('LICENSE.*.txt'))) == 20
        print('PASS: relocated signed app, embedded ' + text.strip() +
              '; synthetic first run/update/watcher; state isolation; worker allowlist; no bundled user data')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('app', type=Path)
    verify(parser.parse_args().app.resolve())
