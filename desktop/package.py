"""Build architecture-specific drag-and-drop DMGs. Never installs or publishes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.2.0'


def package(arch, preview, identity, profile):
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    suffix = '-preview' if preview else ''
    destination = output / f'Weiguang-{VERSION}-macos-{arch}{suffix}.dmg'
    if destination.exists():
        raise ValueError(f'Preserve the existing artifact before rebuilding: {destination.name}')
    if not preview:
        if identity == '-' or not profile:
            raise ValueError('Public release requires Developer ID and a notarytool keychain profile')
        identities = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning'], text=True)
        if not any('Developer ID Application:' in row and identity in row for row in identities.splitlines()):
            raise ValueError('No matching valid Developer ID Application certificate')
    build = ROOT / 'build/packages'
    build.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=arch + '-', dir=build) as temporary:
        directory = Path(temporary)
        content = directory / 'content'
        content.mkdir()
        app = content / '微光.app'
        subprocess.run(['bash', str(ROOT / 'desktop/build.sh')], cwd=ROOT, check=True,
                       env={**os.environ, 'WEIGUANG_ARCH': arch, 'WEIGUANG_APP_OUTPUT': str(app),
                            'WEIGUANG_SIGN_IDENTITY': '-' if preview else identity})
        (content / 'Applications').symlink_to('/Applications', target_is_directory=True)
        note = ('预览版本：仅 ad-hoc 签名，未经过 Apple 公证，macOS 可能拦截。\n'
                'Preview: ad-hoc signed, not notarized; macOS may block opening.\n\n') if preview else ''
        (content / '开始使用 - Start Here.txt').write_text(note +
            'macOS 13+ · ' + arch + '\n\n'
            '1. 将微光.app 拖入 Applications，再从应用目录打开。\n'
            '2. 首次引导中选择一份 Codex 会话记录，并给任务命名。\n'
            '3. 将接入说明复制给当前助手，用于更新任务阶段。\n'
            '无需安装 Python、Xcode 或克隆源码。仍需安装 Codex 并打开目标对话。\n'
            '微信可选，需要支持 iLink/ClawBot 的本人账号及可用的 Codex 控制接口。\n'
            '更新前退出旧 App；拖放替换不会迁移微信凭据或启用登录自启动。\n\n'
            '1. Drag 微光.app to Applications, then open it there.\n'
            '2. Select one Codex transcript and name your task in the setup guide.\n'
            '3. Copy the progress instructions into that Codex conversation.\n'
            'Python, Xcode and a source checkout are not required to run this app.\n'
            'Codex and an open target conversation are required. WeChat is optional.\n', encoding='utf-8')
        image = directory / 'Weiguang.dmg'
        subprocess.run(['hdiutil', 'create', '-quiet', '-volname', '微光 ' + VERSION,
                        '-srcfolder', str(content), '-fs', 'HFS+', '-format', 'UDZO', str(image)], check=True)
        if not preview:
            subprocess.run(['codesign', '--force', '--sign', identity, '--timestamp', str(image)], check=True)
            submission = subprocess.run(['xcrun', 'notarytool', 'submit', str(image), '--keychain-profile', profile,
                                         '--wait', '--output-format', 'json'], check=True, capture_output=True, text=True)
            result = json.loads(submission.stdout)
            (output / f'notarization-{arch}.json').write_text(json.dumps(result, indent=2) + '\n')
            if result.get('status') != 'Accepted':
                raise ValueError('Apple did not accept the submission; no release artifact was produced')
            subprocess.run(['xcrun', 'stapler', 'staple', str(image)], check=True)
            subprocess.run(['xcrun', 'stapler', 'validate', str(image)], check=True)
        subprocess.run(['hdiutil', 'verify', '-quiet', str(image)], check=True)
        image.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=['arm64', 'x86_64', 'both'], default='arm64')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview', action='store_true')
    mode.add_argument('--release', action='store_true')
    parser.add_argument('--identity', default='-')
    parser.add_argument('--notarize-profile')
    args = parser.parse_args()
    for arch in (['arm64', 'x86_64'] if args.arch == 'both' else [args.arch]):
        print(package(arch, args.preview, args.identity, args.notarize_profile))
    artifacts = sorted((ROOT / 'dist').glob('Weiguang-*.dmg'))
    (ROOT / 'dist/SHA256SUMS').write_text(''.join(
        hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n' for path in artifacts))


if __name__ == '__main__':
    main()
