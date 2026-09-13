"""Check a frozen release. This is not an authenticity check for mutable staging."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

root = Path(__file__).resolve().parent
manifest = json.loads((root / 'SHA256.json').read_text())
for name, expected in manifest.items():
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or str(relative) != name:
        raise SystemExit('Invalid manifest path')
    if not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise SystemExit('Invalid manifest digest')
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise SystemExit('Missing or linked bundle file: ' + name)
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit('Bundle file changed: ' + name)
actual = {str(p.relative_to(root)) for directory in ('server', 'wheelhouse')
          for p in (root / directory).rglob('*') if p.is_file() or p.is_symlink()}
expected = {name for name in manifest if name.startswith(('server/', 'wheelhouse/'))}
if actual != expected:
    raise SystemExit('Unexpected or missing installable files in the bundle')
print(f'Verified {len(manifest)} bundle files.')
