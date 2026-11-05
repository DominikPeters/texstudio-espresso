import plistlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import macos_icon


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
