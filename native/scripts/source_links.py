"""Publish source references and small build metadata, without dependency payloads."""
import json
from pathlib import Path
import zipfile


def source_information(sources, output, revision, engine, packaging_revision=None):
    records = {}
    for source in sources.values():
        for entry in source['manifest']['inputs']:
            if not entry.get('url', '').startswith('https://') or not entry.get('sha256'):
                raise ValueError('Missing exact HTTPS source reference: ' + entry['name'])
            key = (entry['url'], entry['sha256'])
            records[key] = {k: v for k, v in entry.items() if k not in ('sourceFile', 'archiveMember')}
    records = sorted(records.values(), key=lambda r: r['name'])
    info = {'editor': {'revision': revision, 'url': 'https://github.com/DominikPeters/texstudio-espresso/tree/' + revision},
            'engine': {'revision': engine, 'url': 'https://github.com/DominikPeters/texpresso/tree/' + engine},
            'dependencies': records}
    if packaging_revision:
        info['packaging'] = {'revision': packaging_revision, 'url': 'https://github.com/DominikPeters/texstudio-espresso/tree/' + packaging_revision}
    (output / 'source-manifest.json').write_text(json.dumps(info, indent=2) + '\n')
    with zipfile.ZipFile(output / 'source-info.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr('source-manifest.json', json.dumps(info, indent=2) + '\n')
        archive.writestr('README.md', 'TeXstudio Espresso source and build information\n\n'
            'Project/engine/dependency sources are linked in source-manifest.json at exact revisions or versions.\n'
            'Platform directories preserve the original build recipes, patches and configuration; license notices accompany the app and project source.\n'
            'No dependency source archives or application binaries are included. See the linked project native/ docs to build.\n')
        for target, source in sorted(sources.items()):
            with zipfile.ZipFile(source['file']) as original:
                for member in original.infolist():
                    name = member.filename
                    if member.is_dir() or not (name.startswith(('recipes/', 'patches/')) or name in ('SOURCE-MANIFEST.json', 'editor-CMakeCache.txt', 'editor-compiler-flags.txt')):
                        continue
                    if Path(name).is_absolute() or '..' in Path(name).parts:
                        raise ValueError('Unsafe build metadata path')
                    if member.file_size > 10 * 1024 * 1024:
                        raise ValueError('Unexpected large build metadata: ' + name)
                    archive.writestr(target + '/' + name, original.read(member))
    return info
