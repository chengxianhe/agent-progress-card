"""Generate an explicit per-user launchd job; installation is a separate user action."""
import argparse
from pathlib import Path
import plistlib

LABEL = 'io.github.chengxianhe.agentprogresscard.wechat'


def configuration(app, card):
    app, card = Path(app), Path(card)
    if not app.is_absolute() or not card.is_absolute():
        raise ValueError('Absolute paths required')
    return {'Label': LABEL,
            'ProgramArguments': [str(app / 'Contents/MacOS/weiguang-cli'), '--resident', '--card-dir', str(card)],
            'EnvironmentVariables': {'WEIGUANG_STATE_DIR': str(card), 'PYTHONDONTWRITEBYTECODE': '1',
                                     'SSL_CERT_FILE': '/etc/ssl/cert.pem'},
            'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 30, 'ExitTimeOut': 45,
            'ProcessType': 'Background'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--card-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_bytes(plistlib.dumps(configuration(args.app, args.card_dir)))
