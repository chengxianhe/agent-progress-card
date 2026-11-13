"""Isolated entry for packaged workers; never import a user-supplied module name."""
import os
from pathlib import Path
import runpy
import sys

ALLOWED = {'agent_progress_card', 'agent_progress_card.watcher', 'agent_progress_card.setup_session',
           'agent_progress_wechat.card_choice', 'agent_progress_wechat.relay', 'agent_progress_wechat.resident'}
if len(sys.argv) < 2 or sys.argv[1] not in ALLOWED:
    raise SystemExit('Unsupported application worker')
resources = str(Path(__file__).resolve().parent)
os.environ.pop('PYTHONHOME', None)
os.environ['PYTHONPATH'] = resources
os.environ['PYTHONNOUSERSITE'] = '1'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ.setdefault('SSL_CERT_FILE', '/etc/ssl/cert.pem')
sys.path.insert(0, resources)
module = sys.argv[1]
sys.argv = [module, *sys.argv[2:]]
runpy.run_module(module, run_name='__main__')
