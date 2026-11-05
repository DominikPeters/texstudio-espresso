"""Product version and runtime requirements recorded from the actual package."""
import argparse
import json
from pathlib import Path
import re

from common import ROOT, run


def version():
    header = (ROOT / 'src/productversion.h').read_text()
    def value(name):
        return re.search(r'^#define ' + name + r' "([^"]+)"', header, re.M)[1]
    base = value('TEXSTUDIO_UPSTREAM_VERSION')
    revision = value('TEXSTUDIO_ESPRESSO_REVISION')
    return {'base': base, 'revision': revision, 'version': base + '-espresso-' + revision}


def macos_load_versions(output):
    values = []
    for block in re.findall(r'cmd LC_(?:BUILD_VERSION|VERSION_MIN_MACOSX)\b(.*?)(?=Load command|\Z)', output, re.S):
        match = re.search(r'\b(?:minos|version)\s+(\d+(?:\.\d+)+)', block)
        if match:
            values.append(match[1])
    return values


def macos_requirements(app, binaries):
    records = []
    for file in binaries:
        values = macos_load_versions(run(['otool', '-l', file], capture=True))
        if not values:
            raise ValueError(f'Missing macOS deployment target: {file}')
        records.append({'path': str(file.relative_to(app)), 'minimum': max(values, key=version_key)})
    if not records:
        raise ValueError('No packaged Mach-O binaries')
    minimum = max((r['minimum'] for r in records), key=version_key)
    return {'minimumMacOSVersion': minimum, 'basis': 'Maximum Mach-O deployment target across every shipped code image',
            'binaries': records}


def version_key(value):
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (3 - len(parts))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field', choices=['base', 'revision', 'version'])
    args = parser.parse_args()
    print(version()[args.field] if args.field else json.dumps(version()))
