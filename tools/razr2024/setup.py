#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install pinned local tools; never talks to or modifies a phone."""
import json
import pathlib
import plistlib
import shutil
import subprocess
import sys
import venv

ROOT = pathlib.Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.razr-runtime'


def library_source(source):
    marker = '\nloadState();\nconst parsed = parseCliArgs(process.argv);'
    if source.count(marker) != 1:
        raise ValueError('Pinned MFD entry point changed; refusing to adapt unknown source')
    prefix, entry = source.split(marker)
    prefix = prefix.removeprefix('#!/usr/bin/env node\n')
    exports = 'loadState, saveState, getLoginUrl, fetchRsaKey, apiRequest, session'
    return ('import {pathToFileURL} from "node:url";\n' + prefix +
            '\nexport {' + exports + '};\n' +
            'if (import.meta.url === pathToFileURL(resolve(process.argv[1] || "")).href) {' +
            marker + entry + '\n}\n')


def main():
    if sys.version_info < (3, 11):
        raise SystemExit('Python 3.11 or newer is required.')
    required = ['git', 'node', 'adb', 'fastboot']
    if sys.platform == 'darwin':
        required.append('xcrun')
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise SystemExit('Install the prerequisites first: ' + ', '.join(missing))
    node_version = subprocess.check_output(['node', '--version'], text=True).strip()
    if int(node_version.lstrip('v').split('.')[0]) < 22:
        raise SystemExit('Node.js 22 or newer is required for the pinned firmware client.')
    RUNTIME.mkdir(exist_ok=True)
    auth = ROOT / '.razr-work/auth'
    auth.mkdir(parents=True, exist_ok=True, mode=0o700)
    auth.chmod(0o700)
    profile = json.loads((ROOT / 'tools/razr2024/profile.json').read_text())
    dependency = RUNTIME / 'mfd'
    if not dependency.exists():
        subprocess.run(['git', 'clone', '--no-checkout', '--filter=blob:none',
                        'https://github.com/JoshRob297/moto-firmware-downloader.git', str(dependency)], check=True)
        subprocess.run(['git', '-C', str(dependency), 'checkout', '--detach', profile['mfd_revision']], check=True)
    revision = subprocess.check_output(['git', '-C', str(dependency), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != profile['mfd_revision']:
        raise SystemExit('Existing runtime uses a different MFD revision; move it aside and rerun setup.')
    original = subprocess.check_output(['git', '-C', str(dependency), 'show', 'HEAD:mfd-cli.mjs'], text=True, encoding='utf-8')
    (dependency / 'mfd-cli.mjs').write_text(library_source(original), encoding='utf-8')
    env = RUNTIME / 'venv'
    venv.EnvBuilder(with_pip=True).create(env)
    python = env / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', 'capstone==5.0.9', 'pyasn1==0.6.5'], check=True)
    node = shutil.which('node')
    (RUNTIME / 'config.json').write_text(json.dumps({'node': node}))
    if sys.platform != 'darwin':
        print('Setup complete. The guided launcher can now prepare the exact firmware.')
        return
    app = RUNTIME / 'MFD Login.app'
    executable = app / 'Contents/MacOS/MFDLogin'
    executable.parent.mkdir(parents=True, exist_ok=True)
    plist = {'CFBundleIdentifier': 'org.emrickk.valhalla.razrlogin', 'CFBundleName': 'MFD Login',
             'CFBundleExecutable': 'MFDLogin', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1',
             'NodeExecutable': node,
             'CFBundleURLTypes': [{'CFBundleURLName': 'Software Fix login', 'CFBundleURLSchemes': ['softwarefix']}]}
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
    subprocess.run(['xcrun', 'swiftc', str(ROOT / 'tools/razr2024/macos/LoginHelper.swift'), '-o', str(executable)], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    subprocess.run(['/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister',
                    '-f', str(app)], check=True)
    print('Setup complete. Run: python3 tools/razr2024/unlock.py prepare')


if __name__ == '__main__':
    main()
