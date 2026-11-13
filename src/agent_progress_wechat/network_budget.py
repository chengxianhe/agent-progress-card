"""Bound the complete DNS/TLS/HTTP operation, not just individual socket reads."""
import json
from pathlib import Path
import subprocess
import sys


def request(base, endpoint, body=None, token='', timeout=35):
    from .ilink import LinkError, trusted_base
    base = trusted_base(base)
    if type(timeout) not in (int, float) or not 0 < timeout <= 60:
        raise LinkError('微信请求时限无效')
    read_timeout = min(timeout, 15) if endpoint == 'sendmessage' else timeout
    budget = min(65, read_timeout + 5)
    bootstrap = "import runpy,sys;sys.path.insert(0,sys.argv[1]);runpy.run_module('agent_progress_wechat.network_worker',run_name='__main__')"
    args = [sys.executable, '-I', '-B', '-c', bootstrap, str(Path(__file__).resolve().parents[1])]
    payload = json.dumps(dict(base=base, endpoint=endpoint, body=body, token=token, timeout=read_timeout), ensure_ascii=False)
    if len(payload.encode()) > 4 * 1024 * 1024:
        raise LinkError('微信请求内容过大')
    try:
        result = subprocess.run(args, input=payload.encode(), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=budget, check=False)
        if result.returncode != 0 or len(result.stdout) > 4 * 1024 * 1024:
            raise ValueError()
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise ValueError()
        if value.get('ok') is True and isinstance(value.get('value'), dict):
            return value['value']
        error = value.get('error', {})
        if (not isinstance(error, dict) or type(error.get('expired')) is not bool
                or type(error.get('stale_context')) is not bool or not isinstance(error.get('message'), str)
                or len(error['message']) > 200):
            raise ValueError()
        from agent_progress_card.sanitize import clean_text
        raise LinkError(clean_text(error['message'], 200), error['expired'], error['stale_context'])
    except LinkError:
        raise
    except subprocess.TimeoutExpired:
        raise LinkError('微信网络操作超过本地总时限，已结束等待') from None
    except (OSError, ValueError, TypeError):
        raise LinkError('微信网络工作进程异常') from None
