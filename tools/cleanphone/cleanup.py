# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small allowlist, user-0 disable only, write-ahead undo journal."""
import hashlib
import json
import os
from pathlib import Path

from tools.razr2024 import unlock as workflow

PACKAGES = json.loads(Path(__file__).with_name('packages.json').read_text())
ALLOWED = {item['id'] for item in PACKAGES}
STATE = Path(__file__).resolve().parents[2] / '.clean-phone'


def shell(serial, *args):
    return workflow.run(['adb', '-s', serial, 'shell', *args], timeout=30)


def package_set(serial, flag=None):
    args = ['pm', 'list', 'packages', '--user', '0']
    if flag:
        args.append(flag)
    output = shell(serial, *args)
    if any(word in output.lower() for word in ('error:', 'exception', 'failure')):
        raise RuntimeError('Could not read package state; no cleanup performed.')
    return {line[8:].strip() for line in output.splitlines() if line.startswith('package:')}


def candidates(serial):
    enabled = package_set(serial, '-e')
    return [item for item in PACKAGES if item['id'] in enabled]


def journal_path(serial):
    # A local hash separates devices without storing their raw serials.
    key = hashlib.sha256(serial.encode()).hexdigest()
    return STATE / (key + '.json')


def load_journal(serial):
    path = journal_path(serial)
    if not path.exists():
        return {'version': 1, 'packages': {}}
    data = json.loads(path.read_text())
    if (not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('packages'), dict)
            or not set(data['packages']).issubset(ALLOWED)
            or any(value not in {'pending', 'disabled'} for value in data['packages'].values())):
        raise RuntimeError('Unrecognized cleanup journal. Keep it for manual recovery; no apps changed.')
    return data


def save_journal(serial, data):
    STATE.mkdir(exist_ok=True, mode=0o700)
    path = journal_path(serial)
    temporary = path.with_suffix('.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(data, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def disable(serial, selected):
    if not set(selected).issubset(ALLOWED):
        raise RuntimeError('Only the reviewed cleanup list is allowed.')
    data = load_journal(serial)
    enabled = package_set(serial, '-e')
    results = []
    for package in dict.fromkeys(selected):
        if package not in enabled:
            results.append((package, 'skipped: not currently enabled'))
            continue
        data['packages'][package] = 'pending'
        save_journal(serial, data)
        shell(serial, 'pm', 'disable-user', '--user', '0', package)
        if package not in package_set(serial, '-d'):
            raise RuntimeError('Disable could not be verified for ' + package + '. Use Restore cleanup to undo any partial work.')
        data['packages'][package] = 'disabled'
        save_journal(serial, data)
        results.append((package, 'disabled and verified'))
    return results


def restore(serial):
    data = load_journal(serial)
    results = []
    for package in list(data['packages']):
        shell(serial, 'pm', 'enable', '--user', '0', package)
        if package not in package_set(serial, '-e'):
            raise RuntimeError('Enable could not be verified for ' + package + '. Journal kept; resolve the connection and try Restore again.')
        del data['packages'][package]
        save_journal(serial, data)
        results.append((package, 'enabled and verified'))
    return results
