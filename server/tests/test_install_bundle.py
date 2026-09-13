"""Release integrity checks. No root privileges or server changes are involved."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

SERVER = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bundle_builder', SERVER / 'build-bundle.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    shutil.copyfile(SERVER / 'verify-bundle.py', source / 'verify-bundle.py')
    (source / 'app.py').write_text('print("example")\n')
    wheels = tmp_path / 'wheels'
    wheels.mkdir()
    (wheels / 'example.whl').write_bytes(b'fixture wheel bytes')
    return source, wheels


def test_frozen_release_is_independent_and_detects_tampering(inputs, tmp_path):
    source, wheels = inputs
    release = tmp_path / 'release.tar.gz'
    expected = builder.build(source, wheels, release)
    snapshot = tmp_path / 'frozen.tar.gz'
    shutil.copyfile(release, snapshot)
    release.write_bytes(b'replaced in staging')
    (source / 'app.py').write_text('raise RuntimeError("changed after freeze")\n')
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == expected
    assert hashlib.sha256(release.read_bytes()).hexdigest() != expected
    frozen = tmp_path / 'frozen'
    frozen.mkdir()
    with tarfile.open(snapshot) as archive:
        assert all(m.isdir() or m.isfile() for m in archive.getmembers())
        archive.extractall(frozen, filter='data')
    command = [sys.executable, '-I', str(frozen / 'verify-bundle.py')]
    subprocess.run(command, check=True, capture_output=True)
    (frozen / 'server/app.py').write_text('tampered')
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0 and 'changed' in result.stderr


def test_links_never_enter_release(inputs, tmp_path):
    source, wheels = inputs
    (source / 'link').symlink_to(source / 'app.py')
    with pytest.raises(ValueError, match='symbolic link'):
        builder.build(source, wheels, tmp_path / 'release.tar.gz')


def test_unlisted_installable_file_is_rejected(inputs, tmp_path):
    source, wheels = inputs
    release = tmp_path / 'release.tar.gz'
    builder.build(source, wheels, release)
    frozen = tmp_path / 'frozen'
    frozen.mkdir()
    with tarfile.open(release) as archive:
        archive.extractall(frozen, filter='data')
    (frozen / 'server/unreviewed.py').write_text('unexpected')
    result = subprocess.run([sys.executable, '-I', str(frozen / 'verify-bundle.py')], capture_output=True, text=True)
    assert result.returncode != 0 and 'Unexpected' in result.stderr
