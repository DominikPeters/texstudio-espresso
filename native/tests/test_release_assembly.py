import gzip
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
                archive.writestr('project/texstudio.tar.gz', gzip.compress(b'editor source', mtime=number))
                archive.writestr('project/texpresso.tar.gz', gzip.compress(b'engine source', mtime=0))
            binary = root / (name + '.' + extension)
            if extension == 'dmg':
                binary.write_bytes(b'disk image fixture')
                binary.with_name(binary.name + '.json').write_text(json.dumps({
                    'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                    'app': {'sourceRevision': 'release-commit', 'engineRevision': 'engine-commit'},
                    'icon': {'AppIconCoffee.icns': 'verified'}, 'applicationsShortcut': '/Applications',
                    'runtimeRequirements': {'minimumMacOSVersion': '15.0'}}))
            elif extension == 'zip':
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
            self.assertEqual(len(list((root / 'assets').iterdir())), 10)
            with zipfile.ZipFile(root / 'assets/source-info.zip') as source:
                self.assertFalse(any(n.startswith(('project/', 'dependency-sources/')) for n in source.namelist()))
                manifest = json.loads(source.read('source-manifest.json'))
                self.assertEqual(manifest['dependencies'][0]['url'], 'https://example.org/library.tar.xz')
                self.assertEqual(manifest['engine']['revision'], 'engine-commit')
            self.assertFalse(any(p.name.endswith('-sources.zip') for p in (root / 'assets').iterdir()))

    def test_stale_source_prevents_release(self):
        for wrong_source, omit_dependency, error in [(True, False, 'Source revision differs')]:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); self.fixtures(root / 'inputs', wrong_source, omit_dependency)
                with patch('assemble_release.run', return_value='engine-commit'):
                    with self.assertRaisesRegex(ValueError, error):
                        assemble(root / 'inputs', root / 'assets', 'release-commit')
