"""Fetch a pinned, relocatable CPython distribution; keep its license files intact."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import shutil
import subprocess
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def checked_members(archive):
    members = archive.getmembers()
    if len(members) > 15000 or sum(m.size for m in members) > 512 * 1024 * 1024:
        raise ValueError('Runtime archive exceeds its extraction budget')
    for member in members:
        name = PurePosixPath(member.name)
        if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0] != 'python':
            raise ValueError('Invalid runtime archive path')
        if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
            raise ValueError('Unsupported runtime archive member')
        member.mode &= 0o777
        if member.issym() or member.islnk():
            link = member.linkname if member.islnk() else str(name.parent / member.linkname)
            normalized = posixpath.normpath(link)
            if PurePosixPath(link).is_absolute() or not normalized.startswith('python/'):
                raise ValueError('Runtime link escapes its prefix')
    return members


def prepare(arch):
    lock = json.loads((ROOT / 'desktop/runtime/python-lock.json').read_text())
    entry = lock['architectures'][arch]
    cache = ROOT / 'build/runtime-cache'
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / 'prepare.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        archive = cache / ('python-' + arch + '.tar.gz')
        if not archive.exists():
            temporary = archive.with_suffix('.partial')
            subprocess.run(['curl', '-fL', '--retry', '2', entry['url'], '-o', str(temporary)], check=True)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Downloaded Python checksum mismatch')
            temporary.replace(archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Cached Python checksum mismatch; remove only this corrupt cache file')
        target = ROOT / 'build/runtime' / arch
        stamp = target / 'source-sha256.txt'
        if stamp.exists() and stamp.read_text().strip() == entry['sha256']:
            if (target / 'python/bin/python3').is_file():
                return target / 'python'
        if target.exists():
            raise ValueError('Runtime cache has a different version; preserve it before rebuilding')
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='runtime-', dir=target.parent) as temp:
            unpacked = Path(temp) / 'unpacked'
            unpacked.mkdir()
            with tarfile.open(archive) as package:
                options = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}
                package.extractall(unpacked, members=checked_members(package), **options)
            if not (unpacked / 'python/bin/python3').is_file():
                raise ValueError('Runtime executable missing')
            (unpacked / 'source-sha256.txt').write_text(entry['sha256'] + '\n')
            unpacked.rename(target)
        return target / 'python'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', choices=['arm64', 'x86_64'], required=True)
    print(prepare(parser.parse_args().arch))
