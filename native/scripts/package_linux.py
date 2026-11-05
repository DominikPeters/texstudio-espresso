#!/usr/bin/env python3
"""Create a co-installable TeXstudio Espresso Debian package from a staged tree."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from common import ROOT, run, sha256
from product_release import version, version_key


def glibc_dependencies(dependencies, required):
    # dpkg-shlibdeps sees the editor's imports. The private engine and bundled
    # libraries can need a newer glibc, which the package manager must enforce.
    match = re.search(r'\blibc6 \(>= (\d+(?:\.\d+)+)[^)]*\)', dependencies)
    if match:
        if version_key(match[1]) >= version_key(required): return dependencies
        return dependencies[:match.start()] + f'libc6 (>= {required})' + dependencies[match.end():]
    return dependencies + f', libc6 (>= {required})'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve(); app = root / 'opt/texstudio-espresso'
    main = app / 'bin/texstudio'
    if not main.is_file(): raise ValueError('Configure the release build with -DCMAKE_INSTALL_PREFIX=/opt/texstudio-espresso')
    arch = run(['dpkg', '--print-architecture'], capture=True)
    # Private engine libraries are bundled; the Qt/PDF GUI uses distro packages.
    dependencies = run(['dpkg-shlibdeps', '--ignore-missing-info', '-O', str(main)], capture=True).strip().removeprefix('shlibs:Depends=')
    if not dependencies or 'libc6' not in dependencies: raise ValueError('Missing system dependency metadata')
    versions = set()
    for file in app.rglob('*'):
        if not file.is_file() or file.is_symlink(): continue
        with file.open('rb') as stream: magic = stream.read(4)
        if magic != b'\x7fELF': continue
        output = run(['readelf', '--version-info', file], capture=True)
        versions.update(re.findall(r'Name: GLIBC_(\d+(?:\.\d+)+)', output))
    required = max(versions, key=version_key)
    dependencies = glibc_dependencies(dependencies, required)
    requirements = {'platform': 'linux', 'architecture': arch, 'minimumGlibcVersion': required,
                    'systemPackages': dependencies, 'texProvider': 'User-installed TeX Live or MiKTeX'}
    data = app / 'share/texstudio'; data.mkdir(parents=True, exist_ok=True)
    (data / 'runtime-requirements.json').write_text(json.dumps(requirements, indent=2) + '\n')
    launcher = root / 'usr/bin/texstudio-espresso'; launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec /opt/texstudio-espresso/bin/texstudio "$@"\n'); launcher.chmod(0o755)
    desktop = root / 'usr/share/applications/org.texstudio.espresso.desktop'; desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=TeXstudio Espresso\nComment=LaTeX editor with live TeXpresso preview\n'
                       'Exec=texstudio-espresso %F\nIcon=texstudio-espresso\nCategories=Office;Publishing;\nMimeType=text/x-tex;\nTerminal=false\n')
    icon = root / 'usr/share/icons/hicolor/512x512/apps/texstudio-espresso.png'; icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'site/icon.png', icon)
    control = root / 'DEBIAN'; control.mkdir(exist_ok=True)
    (control / 'control').write_text(f'Package: texstudio-espresso\nVersion: {version()["version"]}\nSection: editors\nPriority: optional\n'
        f'Architecture: {arch}\nMaintainer: Dominik Peters <3543224+DominikPeters@users.noreply.github.com>\nDepends: {dependencies}\n'
        'Homepage: https://pref.tools/texstudio-espresso/\nDescription: TeXstudio Espresso LaTeX editor with live TeXpresso compilation\n'
        ' Uses a separately installed TeX Live or MiKTeX package distribution.\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    run(['dpkg-deb', '--root-owner-group', '--build', root, args.output])
    args.output.with_name(args.output.name + '.sha256').write_text(sha256(args.output) + '  ' + args.output.name + '\n')
    args.output.with_name(args.output.name + '-requirements.json').write_text(json.dumps(requirements, indent=2) + '\n')


if __name__ == '__main__': main()
