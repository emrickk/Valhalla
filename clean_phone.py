#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guided Motorola MTK inspection, exact-build unlock, and reversible cleanup."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys

from tools.razr2024 import unlock as workflow
from tools.cleanphone import cleanup

ROOT = Path(__file__).resolve().parent
PROFILE = workflow.PROFILE
ABOUT = '''Valhalla Clean Phone - preview 0.1
One guide: check phone -> optional exact-build unlock -> review cleanup -> undo.

Unlock: XT2453V / W1UCS36H.96-35-12-5 only. ERASES DATA; bootloader work can brick.
Cleanup: reviewed optional apps on Motorola MediaTek; no unlock/root/reset needed.
This keeps Motorola Android. It does not install a ROM or remove a carrier SIM lock.
One underlying Razr hardware unlock verified; new guided flow needs more hardware validation.
Instructions: https://github.com/emrickk/Valhalla/blob/main/docs/getting-started.md
'''


def require(*names):
    missing = [name for name in names if not shutil.which(name)]
    if missing:
        raise RuntimeError('Missing: ' + ', '.join(missing) + '. Install prerequisites from docs/getting-started.md, then reopen this terminal.')


def inspect_phone():
    require('adb')
    android = workflow.devices('adb')
    fastboot = workflow.devices('fastboot') if shutil.which('fastboot') else []
    found = set(android + fastboot)
    if len(found) != 1:
        raise RuntimeError('Connect exactly one phone. Boot Android, enable USB debugging, and accept its Allow USB debugging prompt. Check USB drivers/cable if needed.')
    serial = found.pop()
    if serial in fastboot:
        keys = ['sku', 'product', 'version-bootloader', 'current-slot', 'is-userspace', 'securestate']
        info = {key: workflow.fastboot_var(serial, key) for key in keys}
        info['mode'] = 'fastboot'
    else:
        props = {'manufacturer': 'ro.product.manufacturer', 'sku': 'ro.boot.hardware.sku',
                 'model': 'ro.product.model', 'product': 'ro.product.device',
                 'build': 'ro.build.display.id', 'version-bootloader': 'ro.bootloader',
                 'fingerprint': 'ro.build.fingerprint',
                 'platform': 'ro.board.platform', 'android': 'ro.build.version.release',
                 'flash-locked': 'ro.boot.flash.locked'}
        info = {key: cleanup.shell(serial, 'getprop', prop).strip() for key, prop in props.items()}
        info['mode'] = 'android'
    return serial, info


def eligible(info):
    if info['mode'] == 'fastboot':
        try:
            workflow.check_identity(info)
        except RuntimeError:
            return False
        return True
    return all(info.get(key) == value for key, value in {
        'sku': PROFILE['model'], 'product': PROFILE['product'],
        'fingerprint': PROFILE['fingerprint']}.items())


def show_phone(info):
    for key, value in info.items():
        print(f'  {key}: {value or "unknown"}')
    print('Unlock profile: ' + ('matches; Fastboot checks still apply.' if eligible(info)
                                else 'unsupported: no unlock will be attempted.'))
    print('Device serial and IMEI are omitted from this summary.')


def require_cleanup_phone(info, serial):
    if (info['mode'] != 'android' or info.get('manufacturer', '').lower() != 'motorola'
            or not re.fullmatch(r'mt\d+[a-z0-9_]*', info.get('platform', '').lower())):
        raise RuntimeError('Cleanup needs an authorized Motorola MediaTek phone booted into Android.')
    if cleanup.shell(serial, 'am', 'get-current-user').strip() != '0':
        raise RuntimeError('Switch to the phone owner (user 0) before cleanup. Work and guest profiles are not changed.')
    if cleanup.shell(serial, 'settings', 'get', 'secure', 'user_setup_complete').strip() != '1':
        raise RuntimeError('Finish Android setup before cleanup, then re-enable USB debugging.')


def select_packages(items, answer):
    if not answer.strip():
        return []
    try:
        numbers = [int(value) for value in answer.replace(',', ' ').split()]
    except ValueError:
        raise RuntimeError('Use the displayed numbers separated by spaces. Nothing changed.')
    if any(value < 1 or value > len(items) for value in numbers):
        raise RuntimeError('Selection is outside the displayed list. Nothing changed.')
    return [items[value - 1]['id'] for value in dict.fromkeys(numbers)]


def cleanup_phone(serial, info):
    require_cleanup_phone(info, serial)
    items = cleanup.candidates(serial)
    if not items:
        print('No enabled apps from the reviewed list found. No changes needed.')
        return
    print('\nReview each app. Cleanup disables it for the phone owner and keeps its data.\n'
          'Phone, SMS, launcher, updates, Google services and setup components are outside this list.')
    for number, item in enumerate(items, 1):
        print(f"{number}. {item['name']} [{item['group']}]\n   {item['id']}\n   {item['effect']}")
    selected = select_packages(items, input('Numbers to disable, separated by spaces (Enter cancels): '))
    if not selected:
        print('Cancelled. No apps changed.')
        return
    print('Selected:', ', '.join(selected))
    if input('Type DISABLE to confirm: ').strip() != 'DISABLE':
        print('Cancelled. No apps changed.')
        return
    for package, result in cleanup.disable(serial, selected):
        print(package + ': ' + result)
    print('Cleanup finished. Check your usual apps, calls and notifications.\n'
          'Keep .clean-phone/ for Restore cleanup. Turn off USB debugging when finished.')


def guided_unlock(serial, info):
    if info.get('securestate') == 'flashing_unlocked' or info.get('flash-locked') == '0':
        print('Phone reports it is already unlocked. Use cleanup after booting Android.\n'
              'If a previous unlock was interrupted before stock-LK restoration, use recovery option 5.')
        return
    if not eligible(info):
        raise RuntimeError('No verified unlock profile for this model/build. Do not substitute the Razr image. Cleanup is available independently where compatible.')
    require('adb', 'fastboot', 'git', 'node')
    if sys.platform == 'darwin':
        require('xcrun')
    print('\nUnlock will erase phone data and can brick the phone. Back up first.\n'
          'Charge to at least 50%, keep the cable connected, and allow 12 GB free disk space.\n'
          'Preparation installs pinned tools locally and can download 8.22 GB from Lenovo.\n'
          'You will separately confirm before any flash. Cleanup alone does not need this step.')
    if input('Type PREPARE to continue, or Enter to cancel: ').strip() != 'PREPARE':
        return
    if shutil.disk_usage(ROOT).free < 12_000_000_000:
        raise RuntimeError('Free at least 12 GB on this drive before preparing firmware. Nothing flashed.')
    print('[1/3] Setting up local tools...')
    subprocess.run([sys.executable, str(ROOT / 'tools/razr2024/setup.py')], check=True)
    archive = input('Exact stock ZIP path, or Enter for Lenovo sign-in/download: ').strip().strip('"')
    if archive and not Path(archive).expanduser().is_file():
        raise RuntimeError('ZIP path does not exist. Nothing flashed.')
    print('[2/3] Preparing and verifying the exact firmware. This can take several minutes...')
    workflow.prepare(str(Path(archive).expanduser()) if archive else None)
    print('[3/3] Verifying Fastboot identity and starting the guided unlock...')
    workflow.unlock(serial)
    print('For cleanup: finish Android setup, enable USB debugging again, then choose option 3.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--about', action='store_true', help='Explain capabilities; no device or network access')
    parser.add_argument('--check', action='store_true', help='Read connected phone identity only; no phone changes')
    args = parser.parse_args()
    print(ABOUT)
    if sys.version_info < (3, 11):
        raise RuntimeError('Install Python 3.11 or newer.')
    if args.about:
        return
    if args.check:
        _, info = inspect_phone()
        show_phone(info)
        return
    while True:
        print('\n1 Check phone (read only)\n2 Guided unlock (factory reset)\n'
              '3 Review and disable optional apps\n4 Restore cleanup\n5 Restore exact stock LK (recovery)\n0 Exit')
        choice = input('Choose: ').strip()
        if choice == '0':
            return
        if choice not in {'1', '2', '3', '4', '5'}:
            continue
        try:
            with workflow.operation_lock():
                serial, info = inspect_phone()
                show_phone(info)
                if choice == '2':
                    guided_unlock(serial, info)
                elif choice == '3':
                    cleanup_phone(serial, info)
                elif choice == '4':
                    require_cleanup_phone(info, serial)
                    pending = cleanup.load_journal(serial)['packages']
                    print('Apps recorded for this phone:', ', '.join(pending) or 'none')
                    if pending and input('Type RESTORE to re-enable these apps: ').strip() == 'RESTORE':
                        for package, result in cleanup.restore(serial):
                            print(package + ': ' + result)
                elif choice == '5':
                    if info['mode'] != 'fastboot' or not eligible(info):
                        raise RuntimeError('Recovery requires the exact supported phone in Fastboot. Keep .razr-work intact.')
                    if input('Type RESTORE STOCK to flash the verified original LK: ').strip() == 'RESTORE STOCK':
                        print('Stock LK restored. securestate:', workflow.restore_stock(serial))
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
            # Timeout/CalledProcessError strings can contain a private serial or token.
            print('\nStopped:', 'External command failed or timed out.' if isinstance(error, subprocess.SubprocessError) else str(error))
            print('Keep .razr-work/ and .clean-phone/. For partial unlock use recovery notes; for partial cleanup choose Restore cleanup.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print('Stopped:', 'External command failed or timed out.' if isinstance(error, subprocess.SubprocessError) else str(error), file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print('\nStopped. Keep recovery files. Rerun for recovery or Restore cleanup if interrupted during a change.')
        sys.exit(1)
