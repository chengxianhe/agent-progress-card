import argparse
from pathlib import Path
import plistlib

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--arch', choices=['arm64', 'x86_64'], required=True)
    parser.add_argument('--identity', default='-')
    args = parser.parse_args()
    info = {'CFBundleExecutable': 'AgentProgressCard',
            'CFBundleIdentifier': 'io.github.chengxianhe.agentprogresscard',
            'CFBundleName': '微光', 'CFBundleDisplayName': '微光',
            'CFBundleIconFile': 'AppIcon.icns', 'CFBundlePackageType': 'APPL',
            'CFBundleVersion': '3', 'CFBundleShortVersionString': '0.2.0',
            'LSMinimumSystemVersion': '13.0', 'NSHighResolutionCapable': True,
            'NSHumanReadableCopyright': 'See LICENSE, NOTICE and third-party notices in the app resources.',
            'WeiguangArchitecture': args.arch,
            'WeiguangSigning': 'ad-hoc-preview' if args.identity == '-' else 'developer-id'}
    (args.app / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
