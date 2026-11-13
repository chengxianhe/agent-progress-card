"""Copy the pinned prefix, excluding unused developer-only bin entry points."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def assemble(source, destination):
    metadata = Path(__file__).resolve().parent / 'runtime'
    manifest = json.loads((metadata / 'license-source.json').read_text())
    for name, digest in manifest['files'].items():
        if hashlib.sha256((metadata / 'licenses' / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Runtime license checksum mismatch')
    subprocess.run(['/usr/bin/ditto', str(source), str(destination)], check=True)
    # pip/idle/pydoc/config launchers carry upstream build-machine shebangs and are
    # not app features. Keep the interpreter links and all libraries/license files.
    for path in (destination / 'bin').iterdir():
        if path.name not in {'python', 'python3', 'python3.12'}:
            if path.is_dir() and not path.is_symlink():
                raise ValueError('Unexpected directory in runtime bin')
            path.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    assemble(args.source, args.destination)
