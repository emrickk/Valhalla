#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Exact-build Razr workflow. Preparation is offline; unlock requires physical consent."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.razr-work'
RUNTIME = ROOT / '.razr-runtime'
PROFILE = json.loads((Path(__file__).parent / 'profile.json').read_text())
PATCHER = ROOT / 'val-protocol'


def runtime_python():
    return RUNTIME / 'venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


@contextmanager
def operation_lock():
    (WORK / 'auth').mkdir(parents=True, exist_ok=True, mode=0o700)
    (WORK / 'auth').chmod(0o700)
    with (WORK / 'operation.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.write(b'0')
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def private_write(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
    Path(path).chmod(0o600)


def run(args, *, receipt=None, redact=(), timeout=180):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, text=True, timeout=timeout)
    output = result.stdout + result.stderr
    for value in redact:
        output = output.replace(value, '[redacted]')
    if receipt:
        private_write(WORK / receipt, output)
    if result.returncode:
        raise RuntimeError(output[-3000:] or 'Command failed')
    return output


def fastboot_var(serial, name):
    return parse_var(run(['fastboot', '-s', serial, 'getvar', name], timeout=8), name)


def parse_var(text, name):
    pattern = re.compile(r'^\s*(?:\(bootloader\)\s*)?' + re.escape(name) + r'(?:\[(\d+)\])?:\s*(.*?)\s*$', re.M)
    matches = pattern.findall(text)
    chunks = [(int(index), value) for index, value in matches if index]
    if chunks:
        return ''.join(value for _, value in sorted(chunks))
    return next((value for _, value in matches if value and value not in {'Done', 'not found'}), '')


def check_identity(identity):
    expected = {'product': PROFILE['product'], 'sku': PROFILE['model'],
                'version-bootloader': PROFILE['bootloader'], 'current-slot': 'a', 'is-userspace': 'no'}
    for key, value in expected.items():
        if identity.get(key) != value:
            raise RuntimeError(f'Refusing flash: {key} is {identity.get(key)!r}, expected {value!r}')


def inspect(serial):
    keys = ['product', 'sku', 'version-bootloader', 'current-slot', 'is-userspace', 'securestate']
    identity = {key: fastboot_var(serial, key) for key in keys}
    check_identity(identity)
    return identity


def devices(tool):
    output = run([tool, 'devices'], timeout=10)
    return [line.split()[0] for line in output.splitlines()
            if len(line.split()) >= 2 and line.split()[1] in {'device', 'fastboot'}]


def choose_device(requested=None):
    found = set(devices('fastboot') + devices('adb'))
    if requested:
        if requested not in found:
            raise RuntimeError('Requested phone is not connected or ADB is not authorized.')
        return requested
    if len(found) != 1:
        raise RuntimeError('Connect exactly one authorized phone, or specify --serial.')
    return found.pop()


def wait_fastboot(serial, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if serial in devices('fastboot'):
            return
        time.sleep(1)
    raise RuntimeError('Phone did not return to Fastboot. Keep recovery files; do not blindly reflash.')


def verify_all(path):
    output = run([runtime_python(), PATCHER / 'tools/verify_mtk_image.py', path, '--all'],
                 receipt='image-verification.txt')
    if output.count('Result: VALID') != 5 or 'INVALID' in output:
        raise RuntimeError('All five signed subimages must verify.')


def extract_stock(archive):
    if sha256(archive) != PROFILE['archive_sha256']:
        raise RuntimeError('Stock ZIP does not match the exact tested archive SHA-256. No substitution allowed.')
    with zipfile.ZipFile(archive) as bundle:
        bad = bundle.testzip()
        if bad:
            raise RuntimeError('Corrupt ZIP entry: ' + bad)
        candidates = [name for name in bundle.namelist() if Path(name).name == 'lk.img']
        if len(candidates) != 1:
            raise RuntimeError('Expected one original LK in the archive.')
        stock = WORK / 'stock-lk.img'
        stock.write_bytes(bundle.read(candidates[0]))
    if sha256(stock) != PROFILE['lk_sha256']:
        raise RuntimeError('Original LK hash does not match the verified profile.')
    return stock


def obtain_archive():
    archive = WORK / PROFILE['archive']
    if archive.exists():
        return archive
    node = json.loads((RUNTIME / 'config.json').read_text())['node']
    lookup = WORK / 'download.json'
    command = [node, ROOT / 'tools/razr2024/lmsa.mjs', 'firmware', lookup]
    try:
        run(command)
    except RuntimeError:
        if sys.platform == 'darwin':
            subprocess.run(['open', str(RUNTIME / 'MFD Login.app')], check=True)
            input('In MFD Login, click Start fresh login and finish sign-in in your default browser.\n'
                  'Wait for "Login successful", then press Enter here: ')
        else:
            print('Sign in through the pinned downloader. Follow its browser/callback instructions.\n'
                  'Keep all login URLs and tokens private. See docs/getting-started.md for the local-ZIP alternative.')
            subprocess.run([node, str(RUNTIME / 'mfd/mfd-cli.mjs'), 'login'], check=True)
        run(command)
    result = json.loads(lookup.read_text())
    print('Downloading the exact stock package (8.22 GB). Keep it for recovery.', flush=True)
    partial = archive.with_suffix('.zip.part')
    with urllib.request.urlopen(result['url'], timeout=60) as response, partial.open('wb') as target:
        total = 0
        next_update = 256 * 1024 * 1024
        while chunk := response.read(4 * 1024 * 1024):
            target.write(chunk)
            total += len(chunk)
            if total >= next_update:
                print(f'  Downloaded {total / 1_000_000_000:.2f} GB / about 8.22 GB', flush=True)
                next_update += 256 * 1024 * 1024
    partial.replace(archive)
    lookup.unlink(missing_ok=True)
    return archive


def prepare(archive=None):
    if not runtime_python().exists():
        raise RuntimeError('Run python3 tools/razr2024/setup.py first.')
    archive = Path(archive).resolve() if archive else obtain_archive()
    print('Verifying the archive and original LK…', flush=True)
    stock = extract_stock(archive)
    secret = secrets.token_hex(16)
    patched = WORK / 'unlock-lk.img'
    run([runtime_python(), PATCHER / 'lk_auto_patch.py', stock, '-o', patched,
         '--analysis-dir', WORK / 'analysis', '--preset', 'unlock-serial', '--key-token-secret', secret],
        receipt='patch.txt', redact=[secret], timeout=300)
    verify_all(patched)
    private_write(WORK / 'auth/patch-secret.txt', secret)
    private_write(WORK / 'prepared.json', json.dumps({'archive': str(archive), 'patch_sha256': sha256(patched)}))
    print('Preparation passed. No phone was changed. Run: python3 tools/razr2024/unlock.py unlock')


def verify_prepared():
    manifest = json.loads((WORK / 'prepared.json').read_text())
    if not Path(manifest['archive']).is_file():
        raise RuntimeError('The full recovery archive must still be available.')
    if sha256(manifest['archive']) != PROFILE['archive_sha256']:
        raise RuntimeError('The recovery archive changed after preparation.')
    if sha256(WORK / 'stock-lk.img') != PROFILE['lk_sha256']:
        raise RuntimeError('Original recovery LK is missing or changed.')
    if sha256(WORK / 'unlock-lk.img') != manifest['patch_sha256']:
        raise RuntimeError('Prepared patch changed; rerun prepare.')
    verify_all(WORK / 'unlock-lk.img')


def restore_stock(serial):
    inspect(serial)
    stock = WORK / 'stock-lk.img'
    if sha256(stock) != PROFILE['lk_sha256']:
        raise RuntimeError('Stock recovery LK hash mismatch.')
    run(['fastboot', '-s', serial, 'flash', 'lk_a', stock], receipt='restore-stock.txt', timeout=60)
    run(['fastboot', '-s', serial, 'reboot-bootloader'], timeout=15)
    time.sleep(2)
    wait_fastboot(serial)
    state = fastboot_var(serial, 'securestate')
    private_write(WORK / 'after-stock-restore.txt', 'securestate: ' + state + '\n')
    return state


def unlock(serial=None):
    verify_prepared()
    serial = choose_device(serial)
    if serial not in devices('fastboot'):
        run(['adb', '-s', serial, 'reboot', 'bootloader'], timeout=15)
        wait_fastboot(serial)
    identity = inspect(serial)
    if identity['securestate'] == 'flashing_unlocked':
        print('Phone is already unlocked. No flash or wipe performed.')
        return
    if identity['securestate'] != 'oem_locked':
        raise RuntimeError('Unexpected lock state. No flash performed.')
    size = int(fastboot_var(serial, 'partition-size:lk_a'), 16)
    if (WORK / 'unlock-lk.img').stat().st_size >= size:
        raise RuntimeError('Patched image does not fit LK partition.')
    print('Exact build verified. Unlocking ERASES PHONE DATA and can brick the phone.\n'
          'Have backups and adequate battery (50% or more). Keep the USB cable connected.\n'
          'On this phone: Volume Down navigates Yes/No; Volume Up confirms. Power selects Start on the normal Fastboot menu.')
    if input('Type ERASE AND UNLOCK to proceed: ').strip() != 'ERASE AND UNLOCK':
        raise RuntimeError('Cancelled before flashing.')
    run(['fastboot', '-s', serial, 'flash', 'lk_a', WORK / 'unlock-lk.img'], receipt='flash-patch.txt', timeout=60)
    run(['fastboot', '-s', serial, 'reboot-bootloader'], timeout=15)
    time.sleep(2)
    wait_fastboot(serial)
    inspect(serial)
    secret = (WORK / 'auth/patch-secret.txt').read_text().strip()
    output = run([runtime_python(), PATCHER / 'lk_keygen.py', '--secret', secret,
                  '--serialno', serial, '--count', '1'], redact=[secret])
    key = output.strip().splitlines()[-1].strip()
    if not re.fullmatch(r'[A-Za-z0-9]{20}', key):
        raise RuntimeError('Unexpected key format. Patched LK remains; use restore-stock if cancelling.')
    while True:
        choice = input('Hold the phone. Press Enter when ready for the 30-second unlock prompt, or type cancel: ').strip()
        if choice.lower() == 'cancel':
            state = restore_stock(serial)
            print('Stock LK restored; securestate:', state)
            return
        if serial not in devices('fastboot'):
            raise RuntimeError('Phone left Fastboot. Return with Volume Down + Power; then rerun unlock or restore-stock.')
        print('PROMPT OPENING: Volume Down selects Yes; Volume Up confirms.', flush=True)
        run(['fastboot', '-s', serial, 'oem', 'unlock', key], receipt='unlock.txt', redact=[key], timeout=90)
        wait_fastboot(serial)
        state = fastboot_var(serial, 'securestate')
        if state == 'flashing_unlocked':
            break
        if state != 'oem_locked':
            raise RuntimeError('Unexpected state after unlock: ' + state)
        print('Still locked: the prompt may have timed out. An OKAY reply alone is not success.')
    print('Unlock verified. Restoring the exact original LK…', flush=True)
    if restore_stock(serial) != 'flashing_unlocked':
        raise RuntimeError('Unlock state did not persist after stock restore. Do not claim success.')
    run(['fastboot', '-s', serial, 'reboot'], receipt='reboot-android.txt', timeout=15)
    print('SUCCESS: flashing_unlocked verified after original LK restoration.\n'
          'Finish Android setup after the reset. Root/custom ROM/SIM unlock were not performed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare').add_argument('--firmware-zip')
    commands.add_parser('unlock').add_argument('--serial')
    commands.add_parser('restore-stock').add_argument('--serial')
    args = parser.parse_args()
    with operation_lock():
        if args.command == 'prepare':
            prepare(args.firmware_zip)
        elif args.command == 'unlock':
            unlock(args.serial)
        else:
            serial = choose_device(args.serial)
            print('Stock LK restored; securestate:', restore_stock(serial))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError, KeyboardInterrupt, EOFError) as error:
        print('Stopped:', str(error) if not isinstance(error, subprocess.TimeoutExpired) else 'Command timed out.', file=sys.stderr)
        print('Keep .razr-work intact. If LK was flashed and the phone is in Fastboot, use restore-stock.\n'
              'If the phone is not detected, follow the recovery notes; do not repeat blind writes.', file=sys.stderr)
        sys.exit(1)
