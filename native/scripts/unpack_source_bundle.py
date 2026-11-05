"""Restore a selected platform from the complete offline source bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

from unpack_source_release import unpack


def copy_member(source, name, target):
    with source.open(name) as stream:
        shutil.copyfileobj(stream, target, 1024 * 1024)


def restore(archive_path, platform, output):
    with zipfile.ZipFile(archive_path) as archive, tempfile.TemporaryDirectory(prefix='texstudio-source-') as folder:
        folder = Path(folder)
        bundle = json.loads(archive.read('SOURCE-BUNDLE.json'))
        if platform not in bundle['platforms'] or Path(platform).name != platform:
            raise ValueError('Choose a platform from: ' + ', '.join(bundle['platforms']))
        if output.exists():
            raise ValueError('Source output already exists')
        prefix = 'platforms/' + platform + '/'
        manifest = json.loads(archive.read(bundle['platforms'][platform]))
        source = folder / 'platform.zip'
        with zipfile.ZipFile(source, 'w') as project:
            for name, record in bundle['project'].items():
                with archive.open(name) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != record['sha256']:
                        raise ValueError('Shared project source checksum mismatch: ' + name)
            for info in archive.infolist():
                name = info.filename
                destination = name if name in bundle['project'] else name.removeprefix(prefix) if name.startswith(prefix) else None
                if destination and not info.is_dir():
                    with project.open(destination, 'w', force_zip64=True) as target:
                        copy_member(archive, name, target)
        dependencies = folder / 'dependencies'
        dependencies.mkdir()
        for record in manifest['inputs']:
            if record.get('extractTo') and not record.get('archiveMember'):
                name = record['sourceFile']
                if Path(name).name != name or name in ('.', '..'):
                    raise ValueError('Unsafe dependency source filename')
                with (dependencies / name).open('wb') as target:
                    copy_member(archive, 'dependency-sources/' + name, target)
        editor = unpack(source, output, dependencies)
        for name in ('packaging/README.md', 'packaging/changes.patch'):
            if name in archive.namelist():
                target = output / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('wb') as stream:
                    copy_member(archive, name, stream)
        return editor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', nargs='?', type=Path,
                        default=Path(sys.argv[0]) if sys.argv[0].endswith('.zip') else None)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.archive is None:
        parser.error('Supply the complete source ZIP')
    print('Editable source:', restore(args.archive.resolve(), args.platform, args.output.resolve()))
    print('Build recipes and provenance are restored beside the editor; original dependency archives remain inside the ZIP.')


if __name__ == '__main__':
    main()
