#!/usr/bin/env python3
"""Sign a deployed TeXstudio app, notarize it, staple its ticket, and archive it."""
import argparse
import json
import os
import platform
import re
import tempfile
import time
from pathlib import Path
from common import sha256
from deploy_macos import macho_files, refresh_engine_manifest, verify_dependencies
from notarize import command, imported_identity, notarize, signing_credentials
from macos_icon import verify as verify_icon
from package_macos import create_dmg, inspect_dmg


def staple_ticket(app, reports, action, *, attempts=6):
    # The ticket service can lag behind an Accepted notary result. Preserve
    # both output streams: stapler reports many failures only on stdout.
    for attempt in range(1, attempts + 1):
        result = command(['xcrun', 'stapler', action, '-v', app], check=False)
        (reports / f'stapler-{action}-{attempt}.json').write_text(json.dumps({
            'exitCode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}, indent=2) + '\n')
        if result.returncode == 0:
            return
        detail = (result.stdout + '\n' + result.stderr).strip()[-2000:]
        if result.returncode not in (65, 68, 69, 75) or attempt == attempts:
            raise RuntimeError(f'stapler {action} failed (exit {result.returncode}): {detail}')
        delay = min(15 * attempt, 60)
        print(f'stapler {action} attempt {attempt}/{attempts} failed (exit {result.returncode}); retrying in {delay}s: {detail}', flush=True)
        time.sleep(delay)


def sign_app(app, identity, keychain, *, adhoc=False):
    files = macho_files(app)
    if app / 'Contents/MacOS/texstudio' not in files:
        raise ValueError('Missing TeXstudio executable')
    if not adhoc:
        identity = imported_identity(identity, keychain)
    def sign(target, entitlements=None):
        args = ['codesign', '--force', '--options', '0' if adhoc else 'runtime', '--sign', identity]
        if not adhoc:
            args += ['--timestamp', '--keychain', keychain]
        if entitlements:
            args += ['--entitlements', entitlements]
        command([*args, target])
    # Resolve symlinks rather than signing Qt's framework aliases twice.
    for file in files:
        if file != app / 'Contents/MacOS/texstudio':
            sign(file)
    containers = sorted([p for p in app.rglob('*') if p.is_dir() and not p.is_symlink()
                         and p.suffix in ('.framework', '.app', '.xpc', '.bundle', '.plugin')],
                        key=lambda p: (-len(p.parts), str(p)))
    for directory in containers:
        sign(directory)
    details = command(['codesign', '--display', '--verbose=4', app / 'Contents/Helpers/texpresso/bin/texpresso']).stderr
    team = re.search(r'^TeamIdentifier=(\S+)$', details, re.M)
    if not adhoc and (not team or team[1] == 'not set' or 'Authority=Developer ID Application:' not in details):
        raise ValueError('Expected Developer ID signatures on nested engine code')
    refresh_engine_manifest(app, {'kind': 'ad-hoc' if adhoc else 'developer-id',
                                 'teamId': team[1] if team else None,
                                 'hardenedRuntime': not adhoc, 'secureTimestamp': not adhoc})
    # QJSEngine uses JIT in the editor. Native TeX helpers do not need this.
    entitlements = Path(__file__).resolve().parents[1] / 'profiles/texstudio.entitlements'
    sign(app, entitlements)
    command(['codesign', '--verify', '--deep', '--strict', '--verbose=2', app])
    if not adhoc:
        details = command(['codesign', '--display', '--verbose=4', app]).stderr
        if not team or f'TeamIdentifier={team[1]}' not in details or 'Timestamp=' not in details or not re.search(r'^CodeDirectory .*flags=.*\bruntime\b', details, re.M):
            raise ValueError('Outer application must have the same timestamped Developer ID signature and hardened runtime')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Final DMG or ZIP with a stapled app')
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--timeout', default='20m')
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('Signing and notarization require macOS')
    app = args.app.resolve()
    if args.output.exists() or args.output.suffix not in ('.zip', '.dmg'):
        parser.error('Choose a new .dmg or .zip output path')
    # Inspect all code and dependencies before importing credentials.
    verify_dependencies(app)
    verify_icon(app)
    if not (app / 'Contents/Resources/texpresso/build-manifest.json').is_file():
        parser.error('The application must include its engine runtime')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.reports.mkdir(parents=True, exist_ok=True)
    with signing_credentials() as (identity, keychain):
        sign_app(app, identity, keychain)
        with tempfile.TemporaryDirectory(prefix='texstudio-notary-upload-', dir=os.environ.get('RUNNER_TEMP')) as folder:
            upload = Path(folder) / 'submission.zip'
            command(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, upload])
            notarize(upload, args.reports / 'app', keychain, args.timeout)
            (args.reports / 'submitted-archive.sha256').write_text(sha256(upload) + '\n')
        staple_ticket(app, args.reports, 'staple')
        staple_ticket(app, args.reports, 'validate')
        command(['codesign', '--verify', '--deep', '--strict', '--verbose=2', app])
        command(['spctl', '--assess', '--type', 'execute', '--verbose=2', app])
        # The app ticket survives copying from the DMG and supports offline use.
        if args.output.suffix == '.dmg':
            create_dmg(app, args.output.resolve())
            command(['codesign', '--force', '--sign', imported_identity(identity, keychain),
                     '--timestamp', '--keychain', keychain, args.output.resolve()])
            notarize(args.output.resolve(), args.reports / 'dmg', keychain, args.timeout)
            staple_ticket(args.output.resolve(), args.reports / 'dmg', 'staple')
            staple_ticket(args.output.resolve(), args.reports / 'dmg', 'validate')
            command(['codesign', '--verify', '--strict', args.output.resolve()])
            command(['spctl', '--assess', '--type', 'open', '--context',
                     'context:primary-signature', '--verbose=2', args.output.resolve()])
            report = inspect_dmg(args.output.resolve())
            args.output.with_name(args.output.name + '.json').write_text(json.dumps(report, indent=2) + '\n')
        else:
            command(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, args.output.resolve()])
        args.output.with_name(args.output.name + '.sha256').write_text(f'{sha256(args.output)}  {args.output.name}\n')
    print('Signed, notarized and stapled:', args.output)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
