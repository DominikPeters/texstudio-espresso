#!/usr/bin/env python3
"""Inventory Linux/Windows payloads, collect notices and exact package sources.

Run in the package builder: package-manager metadata is evidence for the actual
installed files copied into the distribution. No developer-host packages are
substituted for the builder's package versions. Downloads require --fetch.
"""
import argparse
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from common import ROOT, run, sha256
from license_evidence import dictionary_evidence, copy_dictionary_notices
from product_release import version, version_key
import source_release


def host_path(value):
    # The UCRT Python is a native Windows process, even inside an MSYS2 shell.
    return Path(run(['cygpath', '-w', str(value)], capture=True)) if sys.platform == 'win32' else Path(value)


def control_fields(text):
    result = {}
    key = None
    for line in text.splitlines():
        if line.startswith((' ', '\t')) and key:
            result[key] += '\n' + line.strip()
        elif ':' in line:
            key, value = line.split(':', 1)
            result[key] = value.lstrip()
    return result


def debian_source(package, source_root):
    source, release = run(['dpkg-query', '-W', '-f=${source:Package}\t${source:Version}', package], capture=True).split('\t')
    data = run(['apt-cache', 'showsrc', '--only-source', source], capture=True)
    records = [control_fields(part) for part in data.split('\n\n')]
    record = next((r for r in records if r.get('Version') == release), None)
    if not record:
        raise ValueError(f'Exact Debian source unavailable: {source}={release}; enable deb-src for the builder repository')
    files = []
    for line in record['Checksums-Sha256'].splitlines():
        if not line.strip(): continue
        digest, size, name = line.split()
        if not re.fullmatch(r'[0-9a-f]{64}', digest) or Path(name).name != name:
            raise ValueError('Invalid apt source record')
        files.append({'name': source + '-' + release + '-' + name,
                      'url': source_root.rstrip('/') + '/' + record['Directory'] + '/' + name, 'sha256': digest})
    return {'name': source, 'version': release, 'records': files}


def pacman_fields(text):
    result = {}
    for chunk in text.split('\n\n'):
        lines = chunk.splitlines()
        if lines and lines[0].startswith('%'):
            result[lines[0].strip('%')] = lines[1:]
    return result


def msys_source(package, cache, fetch):
    metadata = next(host_path('/var/lib/pacman/local').glob(package + '-*/desc'), None)
    if not metadata:
        raise ValueError('Missing installed MSYS2 package metadata: ' + package)
    fields = pacman_fields(metadata.read_text())
    base = fields['BASE'][0]; release = fields['VERSION'][0]
    filename = base + '-' + release.split(':')[-1] + '.src.tar.zst'
    url = 'https://repo.msys2.org/mingw/sources/' + filename
    file = cache / filename
    if not file.exists():
        if not fetch: raise ValueError('Missing MSYS2 source; use --fetch: ' + filename)
        temporary = file.with_name(file.name + '.partial')
        try:
            # Source archive version is bound to the installed package database.
            # Record its full SHA256; preserve the original PKGBUILD and patches.
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as target:
                        shutil.copyfileobj(response, target)
                    break
                except OSError:
                    if attempt == 2: raise
            temporary.rename(file)
        finally:
            temporary.unlink(missing_ok=True)
    return {'name': base, 'version': release, 'records': [
        {'name': base + '-' + release, 'url': url, 'sha256': sha256(file)}]}


def package_notices(package, output, platform):
    if platform == 'linux':
        source = Path('/usr/share/doc') / package.split(':')[0] / 'copyright'
        paths = [source] if source.is_file() else []
    else:
        paths = []
        for line in run(['pacman', '-Ql', package], capture=True).splitlines():
            value = line.split(' ', 1)[1]
            path = host_path(value)
            if path.is_file() and '/share/licenses/' in value: paths.append(path)
    if not paths:
        raise ValueError('Missing installed license notices for ' + package)
    output.mkdir(parents=True)
    copied = []
    for number, source in enumerate(paths):
        target = output / (str(number) + '-' + source.name)
        shutil.copyfile(source, target); copied.append(str(target))
    return copied


def binary_owner(file, platform):
    if platform == 'windows':
        prefix = host_path(os.environ.get('MINGW_PREFIX', '/ucrt64'))
        candidate = prefix / 'bin' / file.name
        if not candidate.is_file():
            matches = list((prefix / 'share/qt6/plugins').rglob(file.name))
            if not matches: raise ValueError('Unknown distributed DLL: ' + str(file))
            candidate = matches[0]
        candidate = run(['cygpath', '-u', candidate], capture=True) if sys.platform == 'win32' else str(candidate)
        return run(['pacman', '-Qqo', candidate], capture=True)
    result = subprocess.run(['dpkg-query', '-S', '*/' + file.name], text=True, capture_output=True)
    with file.open('rb') as stream: actual = stream.read(20)
    owners = set()
    for line in result.stdout.splitlines():
        if ': ' not in line: continue
        name, location = line.split(': ', 1)
        candidate = Path(location)
        if not candidate.is_file(): continue
        with candidate.open('rb') as stream: header = stream.read(20)
        # lib32gcc-s1 is itself an amd64 package but contains 32-bit ELFs.
        # Match ELF class/byte order/machine, not just the package architecture.
        if header[:6] == actual[:6] and header[18:20] == actual[18:20]: owners.add(name)
    owners = sorted(owners)
    architecture = run(['dpkg', '--print-architecture'], capture=True)
    owners = [name for name in owners if ':' not in name or name.rsplit(':', 1)[1] == architecture]
    # Both /lib and /usr/lib paths can appear for the same merged-/usr package.
    if len(owners) != 1: raise ValueError(f'Ambiguous/unowned distributed ELF library: {file}: {owners}')
    return owners[0]


def collect(args):
    root = args.root.resolve(); output = args.output.resolve(); cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    if output.exists(): raise ValueError('Inventory output already exists: ' + str(output))
    output.mkdir(parents=True)
    packages = {}; binaries = []; additional = []; inherited = {}
    if args.engine_evidence:
        inherited = json.loads((args.engine_evidence / 'inventory.json').read_text())
        additional += inherited.get('additionalSources', [])
        shutil.copytree(args.engine_evidence, output / 'engine', dirs_exist_ok=True)
    for file in sorted(root.rglob('*')):
        if not file.is_file() or file.is_symlink(): continue
        with file.open('rb') as stream: magic = stream.read(4)
        is_dll = args.platform == 'windows' and file.suffix.lower() == '.dll'
        is_elf = args.platform == 'linux' and magic == b'\x7fELF'
        if not (is_dll or is_elf): continue
        if 'texpresso-runtime' in file.parts and args.platform == 'windows': continue
        package = None
        # App and helper executables are built from the supplied project sources.
        if is_dll or '.so' in file.name:
            package = binary_owner(file, args.platform)
            if package not in packages:
                record = debian_source(package, args.apt_source_root) if args.platform == 'linux' else msys_source(package, cache, args.fetch)
                notices = package_notices(package, output / 'notices' / package, args.platform)
                packages[package] = {**record, 'noticeFiles': [str(Path(p).relative_to(output)) for p in notices]}
                additional += record['records']
        row = {'path': str(file.relative_to(root)), 'sha256': sha256(file), 'package': package}
        if is_elf:
            values = re.findall(r'Name: GLIBC_(\d+(?:\.\d+)+)', run(['readelf', '--version-info', file], capture=True))
            if values: row['minimumGlibcVersion'] = max(values, key=version_key)
        binaries.append(row)
    if not binaries: raise ValueError('No native binaries found in distribution')
    runtime = args.engine.resolve()
    manifest = json.loads((runtime / 'build-manifest.json').read_text())
    if manifest['engineRevision'] != run(['git', 'rev-parse', 'HEAD:native/texpresso'], cwd=ROOT, capture=True):
        raise ValueError('Distribution engine does not match source gitlink')
    shutil.copytree(runtime / 'notices', output / 'engine-notices')
    shutil.copytree(ROOT / 'native/notices/assets', output / 'assets')
    shutil.copyfile(ROOT / 'native/asset-provenance.json', output / 'assets.json')
    shutil.copyfile(ROOT / 'COPYING', output / 'COPYING')
    shutil.copyfile(ROOT / 'ESPRESSO-CHANGES.md', output / 'MODIFICATIONS.md')
    components = json.loads((ROOT / 'native/license-components.json').read_text())
    for component in components:
        for name in component.get('evidence', []):
            source = ROOT / name
            if not source.is_file():
                raise ValueError('Missing bundled-code notice evidence: ' + name)
            target = output / 'components' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    dictionary_records = json.loads((ROOT / 'native/dictionary-provenance.json').read_text())['dictionaries']
    dictionaries = []
    for archive in root.rglob('*.zip'):
        if not archive.name.endswith(('.dic.zip', '.dat.zip')): continue
        record = dictionary_evidence(archive, dictionary_records)
        copy_dictionary_notices(record, output / 'dictionaries')
        dictionaries.append(record)
    result = {'schema': 1, 'platform': args.platform,
        'release': {'sourceRevision': run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture=True),
                    'engineRevision': manifest['engineRevision'], 'productVersion': version()['version']},
        'engineManifest': manifest, 'packages': {}, 'additionalSources': additional,
        'binaries': binaries, 'packageEvidence': packages, 'dictionaries': dictionaries,
        'sourceComponents': components,
        'releaseWorkRemaining': []}
    if args.platform == 'linux':
        result['runtimeRequirements'] = {'minimumGlibcVersion': max(
            (r['minimumGlibcVersion'] for r in binaries if 'minimumGlibcVersion' in r), key=version_key)}
    else:
        result['runtimeRequirements'] = {'platform': 'windows', 'architecture': 'x86_64', 'requiresWSL2': True,
            'engineMinimumGlibcVersion': inherited['runtimeRequirements']['minimumGlibcVersion'],
            'wslInstallationRequirements': 'https://learn.microsoft.com/windows/wsl/install',
            'qtPackages': {k: v['version'] for k, v in packages.items() if 'qt6-' in k}}
        (root / 'runtime-requirements.json').write_text(json.dumps(result['runtimeRequirements'], indent=2) + '\n')
    (output / 'inventory.json').write_text(json.dumps(result, indent=2) + '\n')
    files = sorted(p for p in output.rglob('*') if p.is_file())
    links = ''.join('<li><a href="' + html.escape(str(p.relative_to(output)), quote=True) + '">' + html.escape(str(p.relative_to(output))) + '</a></li>' for p in files)
    (output / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>TeXstudio Espresso — Licenses and Source</title>'
        '<h1>TeXstudio Espresso — Licenses and Source</h1><p>Original copyright and license notices remain applicable. '
        'This distribution includes GPL, AGPL, LGPL and permissive components; it is not MIT-only.</p>'
        '<p><a href="https://github.com/DominikPeters/texstudio-espresso/releases">Matching project and dependency sources</a></p><ul>' + links + '</ul>')
    print(f'Inventoried {len(binaries)} binaries and {len(packages)} builder packages; {len(dictionaries)} dictionaries')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', required=True, choices=['linux', 'windows'])
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--engine', required=True, type=Path)
    parser.add_argument('--engine-evidence', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cache', type=Path, default=Path('.native-sources/distribution-sources'))
    parser.add_argument('--apt-source-root', default='https://archive.ubuntu.com/ubuntu')
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    collect(args)


if __name__ == '__main__':
    main()
