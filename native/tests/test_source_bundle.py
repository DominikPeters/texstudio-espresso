import json
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from source_bundle import bundle_sources
from unpack_source_bundle import restore
import test_source_restore as source_fixtures
import macos_icon


class CompleteSources(unittest.TestCase):
    def test_combined_archive_deduplicates_and_restores_native_sources_offline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, plan, cache, project, dependencies = source_fixtures.SplitSourceRelease().prepare(root)
            manifest = json.loads((plan / 'manifest.json').read_text())
            combined = root / 'all-sources.zip'
            report = bundle_sources({'macos-arm64': project, 'linux-x86_64': project}, dependencies,
                                    combined, manifest['editorRevision'], manifest['engineRevision'], 'example')
            self.assertEqual(report['dependencySourceCount'], 5)
            with zipfile.ZipFile(combined) as archive:
                self.assertEqual(archive.namelist().count('project/texstudio.tar.gz'), 1)
                self.assertEqual(len([n for n in archive.namelist() if n.startswith('dependency-sources/')]), 6)
                self.assertIsNone(archive.testzip())
            editor = restore(combined, 'macos-arm64', root / 'restored')
            self.assertEqual((editor / 'editor.cpp').read_text(), 'editable editor\n')
            self.assertEqual((editor.parent / 'mupdf/source.c').read_text(), 'editable mupdf')
            self.assertTrue((editor.parent / 'mupdf/thirdparty/lcms2/source.c').is_file())
            self.assertTrue((editor.parent / 'zlib-ng/source.c').is_file())
            with self.assertRaisesRegex(ValueError, 'Choose a platform'):
                restore(combined, '../bad', root / 'bad')

    def test_corrupt_dependency_prevents_combined_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, plan, _, project, dependencies = source_fixtures.SplitSourceRelease().prepare(root)
            manifest = json.loads((plan / 'manifest.json').read_text())
            next(dependencies.glob('*.tar.gz')).write_bytes(b'corrupt')
            output = root / 'all.zip'
            with self.assertRaisesRegex(ValueError, 'Missing or corrupt'):
                bundle_sources({'macos-arm64': project}, dependencies, output,
                               manifest['editorRevision'], manifest['engineRevision'], 'example')
            self.assertFalse(output.exists())
            self.assertFalse(output.with_name(output.name + '.partial').exists())


class ProductIcon(unittest.TestCase):
    def test_installed_icon_names_and_catalog_bytes_match_product_artwork(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary) / 'TeXstudio Espresso.app'
            (app / 'Contents/Resources').mkdir(parents=True)
            (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIconName': 'AppIcon'}))
            with self.assertRaisesRegex(ValueError, 'coffee-cup icon'):
                macos_icon.verify(app)
            macos_icon.install(app)
            self.assertEqual(set(macos_icon.verify(app)), {'AppIconCoffee.icns', 'Assets.car'})
            (app / 'Contents/Resources/Assets.car').write_bytes(b'old catalog')
            with self.assertRaisesRegex(ValueError, 'committed product artwork'):
                macos_icon.verify(app)


if __name__ == '__main__':
    unittest.main()
