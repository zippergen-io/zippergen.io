"""Build a clean, checksummed release archive without executing privileged code."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile


def build(source, wheels, destination):
    source, wheels, destination = Path(source), Path(wheels), Path(destination)
    if destination.exists():
        raise ValueError('Refusing to overwrite a release archive')
    with tempfile.TemporaryDirectory(prefix='zippergen-release-') as temp:
        root = Path(temp)
        for path in source.rglob('*'):
            if any(part in ('__pycache__', '.pytest_cache', '.venv', 'state') for part in path.relative_to(source).parts):
                continue
            if path.is_symlink():
                raise ValueError('Release source contains a symbolic link: ' + str(path))
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError('Release source contains a special file: ' + str(path))
            target = root / 'server' / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (root / 'wheelhouse').mkdir()
        candidates = sorted(wheels.glob('*.whl'))
        if not candidates:
            raise ValueError('The wheelhouse is empty')
        for path in candidates:
            if path.is_symlink() or not path.is_file():
                raise ValueError('Wheel must be a regular file: ' + str(path))
            shutil.copyfile(path, root / 'wheelhouse' / path.name)
        shutil.copyfile(source / 'verify-bundle.py', root / 'verify-bundle.py')
        files = sorted(path for path in root.rglob('*') if path.is_file())
        manifest = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        (root / 'SHA256.json').write_text(json.dumps(manifest, indent=2) + '\n')
        with tarfile.open(destination, 'x:gz') as archive:
            for path in sorted(root.rglob('*')):
                info = archive.gettarinfo(str(path), arcname=str(path.relative_to(root)))
                info.uid = info.gid = 0
                info.uname = info.gname = 'root'
                info.mode = 0o755 if info.isdir() else 0o644
                if info.isdir():
                    archive.addfile(info)
                elif info.isfile():
                    with path.open('rb') as data:
                        archive.addfile(info, data)
                else:
                    raise ValueError('Only regular files and directories may enter a release')
    with tarfile.open(destination) as archive:
        for member in archive.getmembers():
            name = Path(member.name)
            if name.is_absolute() or '..' in name.parts or not (member.isdir() or member.isfile()):
                raise ValueError('Unsafe archive member')
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parent, args.wheelhouse, args.output))


if __name__ == '__main__':
    main()
