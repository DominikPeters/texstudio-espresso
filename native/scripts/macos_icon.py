"""Install and verify the product's committed Icon Composer artwork."""
import plistlib
import shutil
from common import ROOT, sha256


ICON_NAME = 'AppIconCoffee'
ICON_DIRECTORY = ROOT / 'native/icons/alternatives/coffee'


def install(app):
    resources = app / 'Contents/Resources'
    resources.mkdir(parents=True, exist_ok=True)
    for name in (ICON_NAME + '.icns', 'Assets.car'):
        shutil.copy2(ICON_DIRECTORY / name, resources / name)
    path = app / 'Contents/Info.plist'
    info = plistlib.loads(path.read_bytes())
    info.update(CFBundleIconName=ICON_NAME, CFBundleIconFile=ICON_NAME + '.icns')
    path.write_bytes(plistlib.dumps(info))
    (resources / 'AppIcon.icns').unlink(missing_ok=True)
    return verify(app)


def verify(app):
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if info.get('CFBundleIconName') != ICON_NAME or info.get('CFBundleIconFile') != ICON_NAME + '.icns':
        raise ValueError('Application does not select the TeXstudio Espresso coffee-cup icon')
    records = {}
    for name in (ICON_NAME + '.icns', 'Assets.car'):
        file = app / 'Contents/Resources' / name
        if not file.is_file() or sha256(file) != sha256(ICON_DIRECTORY / name):
            raise ValueError('Application icon differs from the committed product artwork: ' + name)
        records[name] = sha256(file)
    return records
