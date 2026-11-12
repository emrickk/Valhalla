# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import clean_phone as guide
from tools.cleanphone import cleanup
from tools.razr2024 import unlock as workflow


class GuideTests(unittest.TestCase):
    def test_eligibility_requires_every_exact_android_value(self):
        info = {'mode': 'android', 'sku': guide.PROFILE['model'], 'product': guide.PROFILE['product'],
                'fingerprint': guide.PROFILE['fingerprint']}
        self.assertTrue(guide.eligible(info))
        for key in info.keys() - {'mode'}:
            self.assertFalse(guide.eligible({**info, key: 'unsupported'}))

    def test_unsupported_unlock_never_sets_up_or_reboots(self):
        with patch.object(guide.subprocess, 'run') as run, patch.object(workflow, 'unlock') as unlock:
            with self.assertRaisesRegex(RuntimeError, 'No verified'):
                guide.guided_unlock('fixture', {'mode': 'android'})
            run.assert_not_called()
            unlock.assert_not_called()

    def test_already_unlocked_skips_preparation(self):
        with patch.object(workflow, 'prepare') as prepare:
            guide.guided_unlock('fixture', {'mode': 'android', 'flash-locked': '0'})
            prepare.assert_not_called()

    def test_cleanup_rejects_wrong_chipset_mode_manufacturer_user_and_setup(self):
        valid = {'mode': 'android', 'manufacturer': 'motorola', 'platform': 'mt6878'}
        for key, value in [('mode', 'fastboot'), ('manufacturer', 'samsung'), ('platform', 'qcom')]:
            with self.assertRaises(RuntimeError):
                guide.require_cleanup_phone({**valid, key: value}, 'fixture')
        for outputs in [['10'], ['0', '0']]:
            with patch.object(cleanup, 'shell', side_effect=outputs), self.assertRaises(RuntimeError):
                guide.require_cleanup_phone(valid, 'fixture')
        with patch.object(cleanup, 'shell', side_effect=['0', '1']):
            guide.require_cleanup_phone(valid, 'fixture')

    def test_no_broad_or_invalid_package_selection(self):
        items = cleanup.PACKAGES[:2]
        self.assertEqual(guide.select_packages(items, ''), [])
        self.assertEqual(guide.select_packages(items, '2,1 2'), [items[1]['id'], items[0]['id']])
        for invalid in ['all', '0', '-1', '3', '1; reboot']:
            with self.assertRaises(RuntimeError):
                guide.select_packages(items, invalid)

    def test_declined_cleanup_makes_no_changes(self):
        with patch.object(guide, 'require_cleanup_phone'), patch.object(cleanup, 'candidates', return_value=cleanup.PACKAGES), \
             patch('builtins.input', side_effect=['1', 'no']), patch.object(cleanup, 'disable') as disable:
            guide.cleanup_phone('fixture', {})
            disable.assert_not_called()


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        handle = patch.object(cleanup, 'STATE', Path(self.directory.name))
        handle.start(); self.addCleanup(handle.stop)
        self.package = 'com.dti.tracfone'

    def test_only_enabled_allowlisted_packages_are_offered(self):
        with patch.object(cleanup, 'package_set', return_value={self.package, 'com.android.phone'}):
            self.assertEqual([item['id'] for item in cleanup.candidates('fixture')], [self.package])

    def test_critical_package_cannot_be_disabled_even_via_direct_call(self):
        with patch.object(cleanup, 'shell') as shell, self.assertRaises(RuntimeError):
            cleanup.disable('fixture', ['com.android.systemui'])
        shell.assert_not_called()

    def test_existing_disabled_apps_are_not_added_to_undo(self):
        with patch.object(cleanup, 'package_set', return_value=set()), patch.object(cleanup, 'shell') as shell:
            cleanup.disable('fixture', [self.package])
            shell.assert_not_called()
        self.assertEqual(cleanup.load_journal('fixture')['packages'], {})

    def test_write_ahead_journal_survives_connection_failure(self):
        with patch.object(cleanup, 'package_set', return_value={self.package}), \
             patch.object(cleanup, 'shell', side_effect=RuntimeError('disconnected')):
            with self.assertRaises(RuntimeError):
                cleanup.disable('fixture', [self.package])
        self.assertEqual(cleanup.load_journal('fixture')['packages'], {self.package: 'pending'})
        self.assertNotIn('fixture', cleanup.journal_path('fixture').read_text())

    def test_failed_verification_is_not_reported_as_success(self):
        with patch.object(cleanup, 'package_set', side_effect=[{self.package}, set()]), \
             patch.object(cleanup, 'shell', return_value='Failure'):
            with self.assertRaisesRegex(RuntimeError, 'could not be verified'):
                cleanup.disable('fixture', [self.package])
        self.assertEqual(cleanup.load_journal('fixture')['packages'], {self.package: 'pending'})

    def test_disable_and_restore_are_verified_and_device_scoped(self):
        with patch.object(cleanup, 'package_set', return_value={self.package}), patch.object(cleanup, 'shell') as shell:
            cleanup.disable('fixture', [self.package, self.package])
            shell.assert_called_once_with('fixture', 'pm', 'disable-user', '--user', '0', self.package)
        self.assertEqual(cleanup.load_journal('fixture')['packages'], {self.package: 'disabled'})
        self.assertEqual(cleanup.load_journal('other-phone')['packages'], {})
        with patch.object(cleanup, 'package_set', return_value={self.package}), patch.object(cleanup, 'shell') as shell:
            cleanup.restore('fixture')
            shell.assert_called_once_with('fixture', 'pm', 'enable', '--user', '0', self.package)
        self.assertEqual(cleanup.load_journal('fixture')['packages'], {})

    def test_restore_failure_keeps_journal_and_can_resume(self):
        cleanup.save_journal('fixture', {'version': 1, 'packages': {self.package: 'pending'}})
        with patch.object(cleanup, 'shell'), patch.object(cleanup, 'package_set', return_value=set()):
            with self.assertRaises(RuntimeError):
                cleanup.restore('fixture')
        self.assertIn(self.package, cleanup.load_journal('fixture')['packages'])

    def test_tampered_journal_cannot_enable_arbitrary_packages(self):
        cleanup.save_journal('fixture', {'version': 1, 'packages': {'com.android.phone': 'disabled'}})
        with patch.object(cleanup, 'shell') as shell, self.assertRaises(RuntimeError):
            cleanup.restore('fixture')
        shell.assert_not_called()

    def test_nonobject_journal_fails_before_device_commands(self):
        cleanup.journal_path('fixture').write_text('[]')
        with patch.object(cleanup, 'shell') as shell, self.assertRaises(RuntimeError):
            cleanup.restore('fixture')
        shell.assert_not_called()


class LockTests(unittest.TestCase):
    def test_second_process_cannot_mutate_until_first_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(workflow, 'WORK', Path(directory)):
            script = ('from pathlib import Path; from tools.razr2024 import unlock as w; '
                      'w.WORK = Path(' + repr(directory) + '); '
                      'ctx=w.operation_lock(); ctx.__enter__(); ctx.__exit__(None,None,None)')
            with workflow.operation_lock():
                result = subprocess.run([sys.executable, '-c', script], cwd=guide.ROOT, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
            result = subprocess.run([sys.executable, '-c', script], cwd=guide.ROOT, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
