#!/usr/bin/env python3
"""Verify complete same-commit platform artifacts and assemble release assets."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

from common import sha256, run
from product_release import version
from source_bundle import bundle_sources


TARGETS = {'macos-arm64': 'dmg', 'macos-x86_64': 'dmg',
           'windows-x86_64': 'zip', 'linux-x86_64': 'deb', 'linux-aarch64': 'deb'}


def assemble(inputs, output, revision, packaging_revision=None):
    output.mkdir(parents=True, exist_ok=False)
    tag = version()['version']; prefix = 'texstudio-espresso-' + tag + '-'
    expected_engine = run(['git', 'rev-parse', revision + ':native/texpresso'], capture=True)
    def copy(file):
        target = output / file.name
        if target.exists():
            if sha256(target) != sha256(file): raise ValueError('Conflicting release asset: ' + file.name)
        else: shutil.copyfile(file, target)
        return target
    sources = {}; binaries = {}
    for target, extension in TARGETS.items():
        name = prefix + target
        candidates = list(inputs.rglob(name + '.' + extension))
        if len(candidates) != 1: raise ValueError('Expected one accepted application artifact: ' + name)
        binaries[target] = copy(candidates[0]).name
        candidates = list(inputs.rglob(name + '-sources.zip'))
        if len(candidates) != 1: raise ValueError('Expected one matching source artifact: ' + name)
        with zipfile.ZipFile(candidates[0]) as archive:
            manifest = json.loads(archive.read('SOURCE-MANIFEST.json'))
            if manifest['editorRevision'] != revision:
                raise ValueError('Source revision differs from release commit: ' + name)
            if manifest['engineRevision'] != expected_engine:
                raise ValueError('Engine source differs from release gitlink: ' + name)
        sources[target] = {'file': candidates[0], 'manifest': manifest}
    dependency_records = {}
    for index in inputs.rglob('index.json'):
        records = json.loads(index.read_text())
        if not isinstance(records, list): continue
        for record in records:
            name = record.get('sourceFile')
            if not name or Path(name).name != name: raise ValueError('Unsafe dependency filename')
            file = index.parent / name
            if sha256(file) != record['sha256']: raise ValueError('Dependency source checksum mismatch: ' + name)
            dependency_records[name] = record
            record['_file'] = file
    for source in sources.values():
        for entry in source['manifest']['inputs']:
            if entry['sourceFile'] not in dependency_records:
                raise ValueError('Required dependency source missing from release: ' + entry['name'])
            if dependency_records[entry['sourceFile']]['sha256'] != entry['sha256']:
                raise ValueError('Required dependency source has a different hash')
    # Keep the dependency cache internal; publish only one complete source archive.
    source_name = 'texstudio-espresso-' + tag + '-sources.zip'
    with tempfile.TemporaryDirectory(dir=output.parent) as folder:
        folder = Path(folder)
        for name, record in dependency_records.items():
            # Hard links avoid copying gigabytes of already verified inputs.
            (folder / name).hardlink_to(record['_file'])
        source_report = bundle_sources({target: item['file'] for target, item in sources.items()},
                                       folder, output / source_name, revision, expected_engine, tag,
                                       packaging_revision)
    base = 'https://github.com/DominikPeters/texstudio-espresso/releases/download/' + tag + '/'
    requirements = {}
    for target in TARGETS:
        if target.startswith('macos'):
            binary = next(inputs.rglob(binaries[target]))
            metadata = json.loads(binary.with_name(binary.name + '.json').read_text())
            if metadata['sha256'] != sha256(output / binaries[target]):
                raise ValueError('Disk image differs from its verified contents: ' + target)
            requirements[target] = metadata['runtimeRequirements']
            app = metadata['app']
            if app['sourceRevision'] != revision or app['engineRevision'] != expected_engine:
                raise ValueError('Packaged macOS application differs from its release source')
            if metadata.get('applicationsShortcut') != '/Applications' or not metadata.get('icon'):
                raise ValueError('Disk image is missing its verified product icon or Applications shortcut')
            if packaging_revision and app.get('packagingRevision') != packaging_revision:
                raise ValueError('Disk image packaging revision differs from its corresponding source')
        elif target.startswith('linux'):
            file = next(inputs.rglob(binaries[target] + '-requirements.json'))
            requirements[target] = json.loads(file.read_text())
        else:
            with zipfile.ZipFile(output / binaries[target]) as archive:
                names = [n for n in archive.namelist() if n.endswith('/runtime-requirements.json')]
                if len(names) != 1: raise ValueError('Missing Windows/WSL runtime requirements')
                requirements[target] = json.loads(archive.read(names[0]))
    (output / 'runtime-requirements.json').write_text(json.dumps(requirements, indent=2) + '\n')
    report = {'version': tag, 'sourceRevision': revision, 'binaries': binaries,
              'sources': source_name, 'dependencySourceCount': source_report['dependencySourceCount'],
              **({'packagingRevision': packaging_revision} if packaging_revision else {})}
    (output / 'release-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    files = sorted(p for p in output.iterdir() if p.is_file())
    (output / 'SHA256SUMS').write_text(''.join(sha256(p) + '  ' + p.name + '\n' for p in files))
    notes = ['# TeXstudio Espresso ' + tag, '',
        'TeXstudio ' + version()['base'] + ' with TeXpresso live compilation and a native Qt preview.', '',
        'Includes continuous scrolling, hyperlinks, precise source synchronization, bibliography/full-build integration, '
        'project sessions, incremental rendering, bounded caches, and TikZ Editor integration.', '', '## Downloads', '']
    for target, name in binaries.items(): notes.append('- [' + target + '](' + base + name + ')')
    notes += ['', 'Install TeX Live or MiKTeX separately. On Windows, install it inside WSL2; the portable Windows app is unsigned.',
        'On macOS, open the DMG and drag TeXstudio Espresso to Applications.',
        'The Linux packages declare their exact system-library dependencies and install alongside upstream TeXstudio.', '',
        'See [runtime requirements](' + base + 'runtime-requirements.json) for requirements derived from the shipped stack.', '',
        '## Licenses and corresponding source', '',
        '[Download the complete source archive](' + base + source_name + '). '
        'It includes the shared editor and pinned engine once, all dependency sources, licenses, '
        'patches and platform-specific build recipes. No additional source download is needed. '
        'See its README for offline restoration instructions.', '',
        'Original component licenses apply, including GPL, AGPL, LGPL and permissive licenses. '
        'This is an independent fork maintained by Dominik Peters.', '',
        'Source commit: `' + revision + '`. File integrity checks: [SHA256SUMS](' + base + 'SHA256SUMS).', '']
    (output.parent / 'release-notes.md').write_text('\n'.join(notes))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--packaging-revision')
    args = parser.parse_args()
    print(json.dumps(assemble(args.inputs, args.output, args.revision, args.packaging_revision), indent=2))
