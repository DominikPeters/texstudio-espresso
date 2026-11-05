import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from product_release import version, macos_load_versions, version_key


class ProductRelease(unittest.TestCase):
    def test_version_has_numeric_base_and_fork_revision(self):
        value = version()
        self.assertRegex(value['base'], r'^\d+\.\d+\.\d+$')
        self.assertRegex(value['revision'], r'^[1-9]\d*$')
        self.assertEqual(value['version'], value['base'] + '-espresso-' + value['revision'])

    def test_macos_targets_ignore_sdk_and_library_versions(self):
        output = '''Load command 1
             cmd LC_BUILD_VERSION
        platform 1
           minos 13.0
             sdk 26.2
Load command 2
             cmd LC_ID_DYLIB
 current version 99.0.0
Load command 3
             cmd LC_VERSION_MIN_MACOSX
         version 14.2
             sdk 15.0
'''
        self.assertEqual(macos_load_versions(output), ['13.0', '14.2'])
        self.assertGreater(version_key('14.0'), version_key('13.9.9'))
        self.assertEqual(version_key('14.0'), version_key('14.0.0'))


class LinuxRuntimeFloor(unittest.TestCase):
    def test_private_runtime_floor_cannot_exceed_package_dependencies(self):
        from package_linux import glibc_dependencies
        self.assertEqual(glibc_dependencies('libc6 (>= 2.38), libqt6core6t64', '2.39'),
                         'libc6 (>= 2.39), libqt6core6t64')
        newer = 'libc6 (>= 2.39-0ubuntu8.6), libqt6core6t64'
        self.assertEqual(glibc_dependencies(newer, '2.38'), newer)
        self.assertEqual(glibc_dependencies(newer, '2.39'), newer)
