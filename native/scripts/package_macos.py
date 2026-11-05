"""Create and inspect a drag-to-Applications disk image in the background."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from common import ROOT, run, sha256
from macos_icon import verify as verify_icon


def create_dmg(app, output):
    if output.exists() or output.suffix != '.dmg':
        raise ValueError('Choose a new .dmg output path')
    if app.name != 'TeXstudio Espresso.app':
        raise ValueError('The disk image app must be named TeXstudio Espresso.app')
    verify_icon(app)
    output.parent.mkdir(parents=True, exist_ok=True)
    run(['dmgbuild', '-s', ROOT / 'native/profiles/dmg-settings.py', '-D', 'app=' + str(app),
         'TeXstudio Espresso', output])
    run(['hdiutil', 'verify', output])


def inspect_dmg(image):
    # Never allow Finder to open the mounted volume during verification.
    with tempfile.TemporaryDirectory(prefix='texstudio-dmg-check-', dir=os.environ.get('RUNNER_TEMP')) as folder:
        mount = Path(folder) / 'volume'
        mount.mkdir()
        run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, image])
        try:
            app = mount / 'TeXstudio Espresso.app'
            shortcut = mount / 'Applications'
            if not shortcut.is_symlink() or os.readlink(shortcut) != '/Applications':
                raise ValueError('Disk image lacks its Applications shortcut')
            if not (mount / '.DS_Store').is_file():
                raise ValueError('Disk image lacks its Finder icon layout')
            icon = verify_icon(app)
            run(['codesign', '--verify', '--deep', '--strict', app])
            run(['xcrun', 'stapler', 'validate', app])
            run(['spctl', '--assess', '--type', 'execute', '--verbose=2', app])
            environment = {k: v for k, v in os.environ.items() if not k.startswith(('QT_', 'DYLD_'))}
            environment.update(QT_QPA_PLATFORM='offscreen', SDL_VIDEODRIVER='dummy')
            subprocess.run([str(app / 'Contents/MacOS/texstudio'), '--version'],
                           env=environment, check=True, timeout=30)
            subprocess.run([str(app / 'Contents/Helpers/texpresso/bin/texpresso'), '-capabilities'],
                           env=environment, check=True, timeout=30)
            resources = app / 'Contents/Resources'
            return {'schema': 1, 'sha256': sha256(image), 'bytes': image.stat().st_size,
                    'app': json.loads((resources / 'texpresso-release.json').read_text()),
                    'runtimeRequirements': json.loads((resources / 'runtime-requirements.json').read_text()),
                    'icon': icon, 'applicationsShortcut': '/Applications'}
        finally:
            run(['hdiutil', 'detach', mount])
