"""Sign nested Mach-O files from the inside out, without --deep signing."""
import argparse
from pathlib import Path
import subprocess

MAGIC = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
         b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xca\xfe\xba\xbf'}


def sign(app, identity):
    flags = ['codesign', '--force', '--sign', identity]
    if identity != '-':
        identities = subprocess.check_output(['security', 'find-identity', '-v', '-p', 'codesigning'], text=True)
        if not any('Developer ID Application:' in row and identity in row for row in identities.splitlines()):
            raise ValueError('A valid Developer ID Application identity is required')
        flags += ['--timestamp', '--options', 'runtime']
    candidates = []
    for path in app.rglob('*'):
        if (path.is_file() and not path.is_symlink()
                and path != app / "Contents/MacOS/AgentProgressCard"):
            with path.open('rb') as stream:
                if stream.read(4) in MAGIC:
                    candidates.append(path)
    for path in sorted(candidates, key=lambda p: len(p.parts), reverse=True):
        subprocess.run([*flags, str(path)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([*flags, str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--identity', default='-')
    args = parser.parse_args()
    sign(args.app, args.identity)
