import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from portable_inventory import control_fields, pacman_fields, debian_source, binary_owner, archived_ubuntu_source, package_notices, collect, source_notices
import subprocess
import tempfile
import hashlib
import json
import zipfile
import tarfile
import io
from types import SimpleNamespace


class PortableInventory(unittest.TestCase):
    def test_multilib_owner_must_match_actual_elf_class(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            elf64 = b'\x7fELF\x02\x01' + bytes(12) + b'\x3e\x00'
            elf32 = b'\x7fELF\x01\x01' + bytes(12) + b'\x03\x00'
            current = root / 'bundled.so'; current.write_bytes(elf64)
            source = root / 'lib64.so'; source.write_bytes(elf64)
            other = root / 'lib32.so'; other.write_bytes(elf32)
            response = subprocess.CompletedProcess([], 0, f'lib32gcc-s1: {other}\nlibgcc-s1:amd64: {source}\n', '')
            with patch('portable_inventory.subprocess.run', return_value=response), patch('portable_inventory.run', return_value='amd64'):
                self.assertEqual(binary_owner(current, 'linux'), 'libgcc-s1:amd64')
    def test_package_metadata_preserves_source_checksums_and_multiline_fields(self):
        fields = control_fields('Package: example\nVersion: 2.1-4\nChecksums-Sha256:\n ' + 'a' * 64 + ' 100 source.tar.xz\nDirectory: pool/main/e/example\n')
        self.assertIn('source.tar.xz', fields['Checksums-Sha256'])
        self.assertEqual(fields['Directory'], 'pool/main/e/example')
        self.assertEqual(pacman_fields('%BASE%\nmingw-w64-qt6-base\n\n%VERSION%\n6.12.0-2\n')['BASE'], ['mingw-w64-qt6-base'])

    def test_debian_sources_must_match_actual_installed_source_version(self):
        metadata = 'Package: example\nVersion: 2.1-3\nChecksums-Sha256:\n ' + 'a' * 64 + ' 100 old.tar.xz\nDirectory: pool/main/e/example\n'
        with patch('portable_inventory.run', side_effect=['example\t2.1-4', metadata]):
            with self.assertRaisesRegex(ValueError, 'Exact Debian source unavailable'):
                debian_source('libexample1', 'https://archive.ubuntu.com/ubuntu')

    def test_debian_source_urls_use_verified_index_names(self):
        metadata = 'Package: example\nVersion: 2.1-4\nChecksums-Sha256:\n ' + 'b' * 64 + ' 100 example_2.1.orig.tar.xz\nDirectory: pool/main/e/example\n'
        with patch('portable_inventory.run', side_effect=['example\t2.1-4', metadata]):
            record = debian_source('libexample1', 'https://archive.ubuntu.com/ubuntu')
        self.assertEqual(record['records'][0]['sha256'], 'b' * 64)
        self.assertEqual(record['records'][0]['url'], 'https://archive.ubuntu.com/ubuntu/pool/main/e/example/example_2.1.orig.tar.xz')

    def test_archived_ubuntu_descriptor_binds_exact_old_source_and_patch(self):
        descriptor = ('-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA512\n\n'
                      'Source: example\nVersion: 1:2.1-4ubuntu1\nChecksums-Sha256:\n '
                      + 'a' * 64 + ' 42 example_2.1.orig.tar.xz\n '
                      + 'b' * 64 + ' 10 example_2.1-4ubuntu1.debian.tar.xz\n'
                      '-----BEGIN PGP SIGNATURE-----\nVersion: GnuPG v1\nsignature\n')
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            (cache / 'example_2.1-4ubuntu1.dsc').write_text(descriptor)
            record = archived_ubuntu_source('example', '1:2.1-4ubuntu1', cache)
        self.assertEqual(record['version'], '1:2.1-4ubuntu1')
        self.assertEqual(len(record['records']), 3)
        self.assertEqual(record['records'][1]['sha256'], 'a' * 64)
        self.assertIn('/1%3A2.1-4ubuntu1/', record['records'][1]['url'])
        self.assertEqual(len(record['records'][0]['sha256']), 64)

    def test_archived_source_cannot_substitute_another_version(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            (cache / 'example_2.1-4.dsc').write_text('Source: example\nVersion: 2.1-3\n')
            with self.assertRaisesRegex(ValueError, 'identity differs'):
                archived_ubuntu_source('example', '2.1-4', cache)

    def test_windows_notice_collection_converts_only_license_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); notice = root / 'LICENSE'; notice.write_text('original notice')
            listing = 'qt /ucrt64/include/QtCore/header.h\nqt /ucrt64/bin/Qt6Core.dll\nqt /ucrt64/share/licenses/qt6-base/LICENSE\n'
            with patch('portable_inventory.run', return_value=listing), patch('portable_inventory.host_path', return_value=notice) as convert:
                result = package_notices('qt', root / 'notices', 'windows')
            convert.assert_called_once_with('/ucrt64/share/licenses/qt6-base/LICENSE')
            self.assertEqual(Path(result[0]).read_text(), 'original notice')

    def test_windows_icu_notice_outside_conventional_license_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); notice = root / 'LICENSE'; notice.write_text('ICU original notice')
            listing = 'icu /ucrt64/include/unicode/platform.h\nicu /ucrt64/share/icu/78.3/LICENSE\n'
            with patch('portable_inventory.run', return_value=listing), patch('portable_inventory.host_path', return_value=notice) as convert:
                result = package_notices('icu', root / 'notices', 'windows')
            convert.assert_called_once_with('/ucrt64/share/icu/78.3/LICENSE')
            self.assertEqual(Path(result[0]).read_text(), 'ICU original notice')

    def test_full_inventory_opens_dictionary_archive_and_copies_bound_notices(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); app = root / 'app'; app.mkdir()
            (app / 'texstudio').write_bytes(b'\x7fELF' + bytes(20))
            engine = root / 'engine'; (engine / 'notices').mkdir(parents=True)
            (engine / 'notices/LICENSE').write_text('engine attribution')
            (engine / 'build-manifest.json').write_text(json.dumps({'engineRevision': 'engine-commit'}))
            (root / 'native/notices/assets').mkdir(parents=True)
            (root / 'native/asset-provenance.json').write_text('{}')
            (root / 'native/license-components.json').write_text('[]')
            (root / 'COPYING').write_text('editor license')
            (root / 'ESPRESSO-CHANGES.md').write_text('modification notice')
            (root / 'NOTICE').write_text('dictionary attribution')
            content = b'word'
            record = {'name': 'sample.dic', 'license': 'MIT',
                      'members': [{'name': 'sample.dic', 'sha256': hashlib.sha256(content).hexdigest()}],
                      'notices': [{'path': 'NOTICE'}]}
            (root / 'native/dictionary-provenance.json').write_text(json.dumps({'dictionaries': [record]}))
            with zipfile.ZipFile(app / 'sample.dic.zip', 'w') as archive:
                archive.writestr('sample.dic', content)
            args = SimpleNamespace(root=app, output=root / 'output', cache=root / 'cache',
                                   engine=engine, engine_evidence=None, platform='linux', fetch=False,
                                   apt_source_root='https://archive.ubuntu.com/ubuntu')
            def command(args, **kwargs):
                if args[0] == 'readelf': return 'Name: GLIBC_2.38'
                return 'engine-commit' if args[-1] == 'HEAD:native/texpresso' else 'editor-commit'
            with patch('portable_inventory.ROOT', root), patch('license_evidence.ROOT', root), patch('portable_inventory.run', side_effect=command):
                collect(args)
            data = json.loads((root / 'output/inventory.json').read_text())
            self.assertEqual(data['dictionaries'], [record])
            self.assertEqual((root / 'output/dictionaries/NOTICE').read_text(), 'dictionary attribution')
            self.assertTrue((root / 'output/index.html').is_file())

    def test_original_notices_from_nested_exact_msys_source_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); upstream = io.BytesIO()
            with tarfile.open(fileobj=upstream, mode='w:gz') as archive:
                data = b'original LGPL terms and copyright'
                member = tarfile.TarInfo('libexample-1.0/COPYINGv3'); member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            file = root / 'example.src.tar.gz'
            with tarfile.open(file, 'w:gz') as archive:
                data = upstream.getvalue()
                member = tarfile.TarInfo('example/upstream.tar.gz'); member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            record = {'name': 'example', 'records': [{'name': 'example', 'url': 'https://example.org/example.src.tar.gz',
                       'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}]}
            with patch('portable_inventory.run', return_value='example /ucrt64/bin/libexample.dll\n'):
                result = package_notices('example', root / 'notices', 'windows', record, root)
            self.assertEqual(len(result), 1)
            self.assertEqual(Path(result[0]).read_bytes(), b'original LGPL terms and copyright')
            self.assertEqual(list(root.glob('source-notices-*')), [])
