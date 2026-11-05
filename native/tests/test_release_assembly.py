import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from assemble_release import assemble, TARGETS
from product_release import version


class ReleaseAssembly(unittest.TestCase):
    def fixtures(self, root, wrong_source=False, omit_dependency=False):
        root.mkdir()
        payload = b'exact dependency source'
        digest = hashlib.sha256(payload).hexdigest()
        dependency = {'name': 'library-original-source', 'url': 'https://example.org/library.tar.xz',
                      'sha256': digest, 'sourceFile': digest + '.source'}
        deps = root / 'dependencies'; deps.mkdir()
        if not omit_dependency:
            (deps / dependency['sourceFile']).write_bytes(payload)
            (deps / 'index.json').write_text(json.dumps([dependency]))
        for number, (target, extension) in enumerate(TARGETS.items()):
            name = 'texstudio-espresso-' + version()['version'] + '-' + target
            manifest = {'editorRevision': 'wrong' if wrong_source and number == 0 else 'release-commit',
                        'engineRevision': 'engine-commit', 'inputs': [dependency]}
            with zipfile.ZipFile(root / (name + '-sources.zip'), 'w') as archive:
                archive.writestr('SOURCE-MANIFEST.json', json.dumps(manifest))
            binary = root / (name + '.' + extension)
            if extension == 'zip':
                with zipfile.ZipFile(binary, 'w') as archive:
                    if target.startswith('macos'):
                        archive.writestr('TeXstudio Espresso.app/Contents/Resources/runtime-requirements.json', '{"minimumMacOSVersion":"15.0"}')
                        archive.writestr('TeXstudio Espresso.app/Contents/Resources/texpresso-release.json', json.dumps(
                            {'sourceRevision': 'release-commit', 'engineRevision': 'engine-commit'}))
                    else:
                        archive.writestr('TeXstudio-Espresso/runtime-requirements.json', '{"requiresWSL2":true}')
            else:
                binary.write_bytes(b'deb package fixture')
                (root / (binary.name + '-requirements.json')).write_text('{"minimumGlibcVersion":"2.39"}')

    def test_draft_requires_every_platform_and_matching_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); self.fixtures(root / 'inputs')
            with patch('assemble_release.run', return_value='engine-commit'):
                report = assemble(root / 'inputs', root / 'assets', 'release-commit')
            self.assertEqual(set(report['binaries']), set(TARGETS))
            self.assertEqual(report['dependencySourceCount'], 1)
            self.assertTrue((root / 'assets/SHA256SUMS').is_file())

    def test_stale_source_and_missing_dependency_prevent_release(self):
        for wrong_source, omit_dependency, error in [(True, False, 'Source revision differs'), (False, True, 'Required dependency source missing')]:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self.fixtures(root / 'inputs', wrong_source, omit_dependency)
                with patch('assemble_release.run', return_value='engine-commit'):
                    with self.assertRaisesRegex(ValueError, error):
                        assemble(root / 'inputs', root / 'assets', 'release-commit')
