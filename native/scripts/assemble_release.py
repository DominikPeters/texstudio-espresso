#!/usr/bin/env python3
"""Verify complete same-commit platform artifacts and assemble release assets."""
import argparse
import html
import json
from pathlib import Path
import shutil
import zipfile

from common import sha256, run
from product_release import version


TARGETS = {'macos-arm64': 'zip', 'macos-x86_64': 'zip',
           'windows-x86_64': 'zip', 'linux-x86_64': 'deb', 'linux-aarch64': 'deb'}


def assemble(inputs, output, revision):
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
        sources[target] = {'file': copy(candidates[0]).name, 'manifest': manifest}
    dependency_records = {}
    for index in inputs.rglob('index.json'):
        records = json.loads(index.read_text())
        if not isinstance(records, list): continue
        for record in records:
            name = record.get('sourceFile')
            if not name or Path(name).name != name: raise ValueError('Unsafe dependency filename')
            file = index.parent / name
            if sha256(file) != record['sha256']: raise ValueError('Dependency source checksum mismatch: ' + name)
            copy(file); dependency_records[name] = record
    for source in sources.values():
        for entry in source['manifest']['inputs']:
            if entry['sourceFile'] not in dependency_records:
                raise ValueError('Required dependency source missing from release: ' + entry['name'])
            if dependency_records[entry['sourceFile']]['sha256'] != entry['sha256']:
                raise ValueError('Required dependency source has a different hash')
    dependency_index = list(dependency_records.values())
    (output / 'dependency-sources-index.json').write_text(json.dumps(dependency_index, indent=2) + '\n')
    base = 'https://github.com/DominikPeters/texstudio-espresso/releases/download/' + tag + '/'
    links = ''.join('<li><a href="' + base + r['sourceFile'] + '">' + html.escape(r['name']) + '</a></li>' for r in dependency_index)
    (output / 'dependency-sources-index.html').write_text('<!doctype html><meta charset="utf-8"><title>TeXstudio Espresso dependency sources</title><h1>Dependency sources</h1><ul>' + links + '</ul>')
    requirements = {}
    for target in TARGETS:
        if target.startswith('macos'):
            with zipfile.ZipFile(output / binaries[target]) as archive:
                names = [n for n in archive.namelist() if n.endswith('/Contents/Resources/runtime-requirements.json')]
                if len(names) != 1: raise ValueError('Missing packaged macOS runtime requirements')
                requirements[target] = json.loads(archive.read(names[0]))
                names = [n for n in archive.namelist() if n.endswith('/Contents/Resources/texpresso-release.json')]
                if len(names) != 1: raise ValueError('Missing packaged macOS source provenance')
                metadata = json.loads(archive.read(names[0]))
                if metadata['sourceRevision'] != revision or metadata['engineRevision'] != expected_engine:
                    raise ValueError('Packaged macOS application differs from its release source')
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
              'projectSources': {k: v['file'] for k, v in sources.items()}, 'dependencySourceCount': len(dependency_records)}
    (output / 'release-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    files = sorted(p for p in output.iterdir() if p.is_file())
    (output / 'SHA256SUMS').write_text(''.join(sha256(p) + '  ' + p.name + '\n' for p in files))
    notes = ['# TeXstudio Espresso ' + tag, '',
        'TeXstudio ' + version()['base'] + ' with TeXpresso live compilation and a native Qt preview.', '',
        'Includes continuous scrolling, hyperlinks, precise source synchronization, bibliography/full-build integration, '
        'project sessions, incremental rendering, bounded caches, and TikZ Editor integration.', '', '## Downloads', '']
    for target, name in binaries.items(): notes.append('- [' + target + '](' + base + name + ')')
    notes += ['', 'Install TeX Live or MiKTeX separately. On Windows, install it inside WSL2; the portable Windows app is unsigned.',
        'The Linux packages declare their exact system-library dependencies and install alongside upstream TeXstudio.', '',
        'See [runtime requirements](' + base + 'runtime-requirements.json) for requirements derived from the shipped stack.', '',
        '## Licenses and corresponding source', '',
        'Each platform has a matching `-sources.zip` asset, including the editor, pinned engine, patches, notices and build recipes. '
        'The separate dependency source archives are reusable across platforms and versions. '
        '[Browse the dependency source index](' + base + 'dependency-sources-index.html) or download its JSON manifest. '
        'Keep the dependency sources required by your platform’s `SOURCE-MANIFEST.json` beside its source ZIP when restoring native inputs.', '',
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
    args = parser.parse_args()
    print(json.dumps(assemble(args.inputs, args.output, args.revision), indent=2))
