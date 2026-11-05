"""Combine exact platform sources into one self-contained, deduplicated ZIP."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from common import ROOT, sha256


def member_hash(archive, name, *, unpack_gzip=False):
    with archive.open(name) as stream:
        if unpack_gzip:
            with gzip.GzipFile(fileobj=stream) as raw:
                return hashlib.file_digest(raw, 'sha256').hexdigest()
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def copy_member(source, name, output, destination):
    info = zipfile.ZipInfo(destination)
    info.compress_type = zipfile.ZIP_STORED if name.endswith(('.gz', '.xz', '.zst', '.zip', '.bz2')) else zipfile.ZIP_DEFLATED
    info.external_attr = source.getinfo(name).external_attr
    with source.open(name) as stream, output.open(info, 'w', force_zip64=True) as target:
        shutil.copyfileobj(stream, target, 1024 * 1024)


def bundle_sources(platforms, dependencies, output, revision, engine, tag, packaging_revision=None):
    if output.exists():
        raise ValueError('Source bundle already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    project = {}; required = {}; manifests = {}
    temporary = output.with_name(output.name + '.partial')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as combined:
            for target, file in sorted(platforms.items()):
                with zipfile.ZipFile(file) as source:
                    manifest = json.loads(source.read('SOURCE-MANIFEST.json'))
                    if manifest['editorRevision'] != revision or manifest['engineRevision'] != engine:
                        raise ValueError('Platform source revisions differ: ' + target)
                    manifests[target] = 'platforms/' + target + '/SOURCE-MANIFEST.json'
                    for record in manifest['inputs']:
                        name = record['sourceFile']
                        if Path(name).name != name or name in ('.', '..'):
                            raise ValueError('Unsafe dependency filename')
                        if name in required and required[name]['sha256'] != record['sha256']:
                            raise ValueError('Conflicting dependency source hashes')
                        required[name] = record
                    for info in source.infolist():
                        name = info.filename
                        if info.is_dir() or name in ('__main__.py', 'unpack_source_release.py', 'README.md'):
                            continue
                        if name.startswith('/') or '..' in Path(name).parts:
                            raise ValueError('Unsafe source archive member')
                        if name.startswith('project/'):
                            # Git tar exports are identical across platforms; gzip headers can differ.
                            content = member_hash(source, name, unpack_gzip=name.endswith('.gz'))
                            if name in project:
                                if project[name]['tarSha256'] != content:
                                    raise ValueError('Shared project source differs across platforms: ' + name)
                                continue
                            project[name] = {'sha256': member_hash(source, name), 'tarSha256': content}
                            destination = name
                        else:
                            destination = 'platforms/' + target + '/' + name
                        copy_member(source, name, combined, destination)
            for name, record in sorted(required.items()):
                file = dependencies / name
                if not file.is_file() or sha256(file) != record['sha256']:
                    raise ValueError('Missing or corrupt dependency source: ' + record['name'])
                combined.write(file, 'dependency-sources/' + name, compress_type=zipfile.ZIP_STORED)
            combined.writestr('dependency-sources/index.json', json.dumps(list(required.values()), indent=2) + '\n')
            metadata = {'schema': 1, 'version': tag, 'editorRevision': revision, 'engineRevision': engine,
                        'platforms': manifests, 'project': project, 'dependencySourceCount': len(required)}
            if packaging_revision:
                metadata['packagingRevision'] = packaging_revision
                patch = subprocess.check_output(['git', 'diff', '--binary', revision, packaging_revision], cwd=ROOT)
                combined.writestr('packaging/changes.patch', patch)
                combined.writestr('packaging/README.md',
                    'The application code retains revision ' + revision + '.\n'
                    'Packaging changes (icon and DMG/source tooling) come from ' + packaging_revision + '.\n'
                    'After restoration, apply: git -C texstudio apply ../packaging/changes.patch\n'
                    'Commit the changes before invoking builders that require a clean checkout.\n')
            combined.writestr('SOURCE-BUNDLE.json', json.dumps(metadata, indent=2) + '\n')
            combined.writestr('README.md', README)
            for name in ('unpack_source_release.py', 'unpack_source_bundle.py'):
                combined.write(ROOT / 'native/scripts' / name, name)
            combined.writestr('__main__.py', 'from unpack_source_bundle import main\nmain()\n')
        # Stream every member, including dependencies, to verify CRCs before publication.
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip():
                raise ValueError('Combined source archive integrity check failed')
        if temporary.stat().st_size >= 2 * 1024 ** 3:
            raise ValueError('Combined source archive exceeds the GitHub release asset size limit')
        temporary.replace(output)
        return metadata
    finally:
        temporary.unlink(missing_ok=True)


README = '''# TeXstudio Espresso complete corresponding source

This single archive contains all five platforms' exact source inputs, notices,
patches, build recipes and inventories. Shared editor/engine sources and identical
dependency archives are stored once. No additional source download is required.

Restore the editor, engine and its native build inputs offline (Python 3.12+, Git):

    python3 this-sources.zip --platform macos-arm64 --output ./source

Other platforms: macos-x86_64, windows-x86_64, linux-x86_64, linux-aarch64.
The helper verifies the selected source hashes before restoring. It does not
install system packages or run build recipes. See the restored native/ docs for
build and signing commands. Apple signing credentials and SDKs are not included.

To inspect all original dependency archives/patches, unzip this file. The readable
names, versions, original URLs and SHA256 hashes are in dependency-sources/index.json.
Each platforms/<platform>/SOURCE-MANIFEST.json records the inputs used there.
project/ contains the shared project exports. SOURCE-BUNDLE.json records revisions.
When packaging/ is present, it contains the additional exact packaging changes
used to repackage existing tested binaries; see packaging/README.md.
'''
