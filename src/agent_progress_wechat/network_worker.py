"""Fixed worker: secrets travel only through stdin; no credentials in argv/logs."""
import json
import sys


def main():
    from .ilink import _request_direct, LinkError
    try:
        raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError()
        args = json.loads(raw)
        if not isinstance(args, dict) or set(args) != {'base', 'endpoint', 'body', 'token', 'timeout'}:
            raise ValueError()
        if not all(isinstance(args[key], str) for key in ('base', 'endpoint', 'token')):
            raise ValueError()
        if type(args['timeout']) not in (float, int) or not 0 < args['timeout'] <= 60:
            raise ValueError()
        value = _request_direct(**args)
        response = {'ok': True, 'value': value}
    except LinkError as error:
        response = {'ok': False, 'error': {'message': str(error), 'expired': error.expired,
                                         'stale_context': error.stale_context}}
    except Exception:
        response = {'ok': False, 'error': {'message': '微信网络工作进程异常', 'expired': False,
                                         'stale_context': False}}
    sys.stdout.write(json.dumps(response, ensure_ascii=False))


if __name__ == '__main__':
    main()
