import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from portable_inventory import control_fields, pacman_fields, debian_source, binary_owner, archived_ubuntu_source, package_notices
import subprocess
import tempfile


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
