#!/usr/bin/env python3
"""Verify existing public release inputs before changing only their packaging."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import re
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

from common import ROOT, run, sha256
from macos_icon import install as install_icon


def download_inputs(tag, output, target=None):
    if not re.fullmatch(r'[A-Za-z0-9._-]+', tag):
        raise ValueError('Invalid release tag')
    release = json.loads(subprocess.check_output([
        'gh', 'api', f'repos/DominikPeters/texstudio-espresso/releases/tags/{tag}'], text=True))
    output.mkdir(parents=True, exist_ok=False)
    (output / 'original-release.json').write_text(json.dumps(release, indent=2) + '\n')
    prefix = 'texstudio-espresso-' + tag + '-'
    if target:
        wanted = {prefix + target + '.zip'}
        assets = [a for a in release['assets'] if a['name'] in wanted]
        if len(assets) != 1:
            raise ValueError('Expected the original Mac ZIP to repackage')
    else:
        assets = [a for a in release['assets'] if
                  not a['name'].startswith(prefix + 'macos-') or a['name'].endswith('-sources.zip')]
    def fetch(asset):
        name = asset['name']
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Unsafe release asset filename')
        digest = asset.get('digest', '')
        if not digest.startswith('sha256:'):
            raise ValueError('Release input has no GitHub SHA256 digest: ' + name)
        file = output / name
        for attempt in range(3):
            try:
                with urllib.request.urlopen(asset['browser_download_url'], timeout=120) as response, file.open('wb') as stream:
                    shutil.copyfileobj(response, stream, 1024 * 1024)
                if file.stat().st_size != asset['size'] or sha256(file) != digest[7:]:
                    raise ValueError('Release input size/checksum mismatch: ' + name)
                return
            except Exception:
                file.unlink(missing_ok=True)
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch, assets))
    if not target:
        records = json.loads((output / 'dependency-sources-index.json').read_text())
        deps = output / 'dependency-sources'
        deps.mkdir()
        for record in records:
            name = record['sourceFile']
            if Path(name).name != name or name in ('.', '..'):
                raise ValueError('Unsafe dependency filename')
            shutil.move(output / name, deps / name)
        (deps / 'index.json').write_text(json.dumps(records, indent=2) + '\n')
        requirements = json.loads((output / 'runtime-requirements.json').read_text())
        for platform in ('linux-x86_64', 'linux-aarch64'):
            name = prefix + platform + '.deb-requirements.json'
            (output / name).write_text(json.dumps(requirements[platform], indent=2) + '\n')
    print(f'Verified {len(assets)} existing release inputs', flush=True)


def update_mac_app(archive, output, packaging_revision):
    run(['ditto', '-x', '-k', archive, output])
    app = output / 'TeXstudio Espresso.app'
    run(['codesign', '--verify', '--deep', '--strict', app])
    run(['xcrun', 'stapler', 'validate', app])
    icon = install_icon(app)
    path = app / 'Contents/Resources/texpresso-release.json'
    metadata = json.loads(path.read_text())
    metadata.update(packagingRevision=packaging_revision, icon=icon)
    path.write_text(json.dumps(metadata, indent=2) + '\n')
    # Retain original library provenance; update only resources changed by packaging.
    path = app / 'Contents/Resources/licenses/inventory.json'
    inventory = json.loads(path.read_text())
    inventory['resources'] = [r for r in inventory['resources'] if (app / r['path']).is_file()]
    changed = ['Contents/Info.plist', 'Contents/Resources/texpresso-release.json',
               'Contents/Resources/AppIconCoffee.icns', 'Contents/Resources/Assets.car']
    for name in changed:
        record = next((r for r in inventory['resources'] if r['path'] == name), None)
        if record is None:
            record = {'path': name, 'category': 'artwork' if name.endswith(('.icns', '.car')) else 'metadata'}
            inventory['resources'].append(record)
        record.update(sha256=sha256(app / name), bytes=(app / name).stat().st_size)
    inventory.update(release=metadata, packagingRevision=packaging_revision,
                     packagingChanges='Coffee-cup app icon; original executable/library build retained; signatures renewed')
    path.write_text(json.dumps(inventory, indent=2) + '\n')
    print('Prepared the original tested app with updated product artwork:', app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    download = sub.add_parser('download')
    download.add_argument('--tag', required=True)
    download.add_argument('--output', type=Path, required=True)
    download.add_argument('--target', choices=['macos-arm64', 'macos-x86_64'])
    update = sub.add_parser('macos-icon')
    update.add_argument('--archive', type=Path, required=True)
    update.add_argument('--output', type=Path, required=True)
    update.add_argument('--packaging-revision', required=True)
    args = parser.parse_args()
    if args.action == 'download':
        download_inputs(args.tag, args.output, args.target)
    else:
        update_mac_app(args.archive, args.output, args.packaging_revision)


if __name__ == '__main__':
    main()
