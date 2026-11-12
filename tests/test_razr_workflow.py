# SPDX-License-Identifier: AGPL-3.0-or-later
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/razr2024' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


workflow = module('razr_unlock', 'unlock.py')
setup = module('razr_setup', 'setup.py')


class IdentityTests(unittest.TestCase):
    def test_wrapped_mbm_version_is_reassembled_in_numeric_order(self):
        value = '(bootloader) version-bootloader[1]: tail\n(bootloader) version-bootloader[0]: head-\nversion-bootloader: Done\n'
        self.assertEqual(workflow.parse_var(value, 'version-bootloader'), 'head-tail')

    def test_unknown_variable_is_not_accepted(self):
        self.assertEqual(workflow.parse_var('(bootloader) unlocked: not found\nunlocked: \n', 'unlocked'), '')

    def test_every_identity_mismatch_is_rejected(self):
        valid = {'product': 'aito', 'sku': 'XT2453V', 'version-bootloader': workflow.PROFILE['bootloader'],
                 'current-slot': 'a', 'is-userspace': 'no'}
        workflow.check_identity(valid)
        for field in valid:
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                workflow.check_identity({**valid, field: 'different'})

    def test_wrong_firmware_is_rejected_before_zip_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'wrong.zip'
            archive.write_bytes(b'not the exact tested image')
            with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                workflow.extract_stock(archive)

    def test_library_adapter_refuses_unknown_source(self):
        with self.assertRaises(ValueError):
            setup.library_source('something else')

    def test_library_adapter_does_not_move_shebang_into_javascript(self):
        source = '#!/usr/bin/env node\n// fixture\nloadState();\nconst parsed = parseCliArgs(process.argv);'
        result = setup.library_source(source)
        self.assertNotIn('#!', result)
        self.assertIn('export {loadState', result)

    def test_failed_repreparation_does_not_replace_last_patch_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            interpreter = root / 'venv' / ('Scripts/python.exe' if workflow.os.name == 'nt' else 'bin/python')
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()
            (root / 'auth').mkdir()
            secret = root / 'auth/patch-secret.txt'
            secret.write_text('previous-fixture-secret')
            with patch.object(workflow, 'RUNTIME', root), patch.object(workflow, 'WORK', root), \
                 patch.object(workflow, 'extract_stock', return_value=root / 'stock-lk.img'), \
                 patch.object(workflow, 'run', side_effect=RuntimeError('Patcher failed')):
                with self.assertRaises(RuntimeError):
                    workflow.prepare(root / 'fixture.zip')
            self.assertEqual(secret.read_text(), 'previous-fixture-secret')


class UnlockFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        work = Path(self.temp.name)
        (work / 'auth').mkdir()
        (work / 'auth/patch-secret.txt').write_text('fixture-secret')
        (work / 'unlock-lk.img').write_bytes(b'fixture-patch')
        self.calls = []

        def run(args, **kwargs):
            self.calls.append([str(arg) for arg in args])
            return 'A' * 20 if 'lk_keygen.py' in str(args[1]) else 'OKAY'

        for name, value in {'WORK': work}.items():
            handle = patch.object(workflow, name, value);handle.start();self.addCleanup(handle.stop)
        for name, kwargs in {
            'verify_prepared': {}, 'choose_device': {'return_value': 'FIXTURE123'},
            'devices': {'return_value': ['FIXTURE123']}, 'inspect': {'return_value': {'securestate': 'oem_locked'}},
            'wait_fastboot': {}, 'run': {'side_effect': run}, 'restore_stock': {'return_value': 'flashing_unlocked'},
        }.items():
            handle = patch.object(workflow, name, **kwargs);handle.start();self.addCleanup(handle.stop)
        handle = patch.object(workflow.time, 'sleep');handle.start();self.addCleanup(handle.stop)

    def test_decline_never_flashes(self):
        with patch.object(workflow, 'fastboot_var', return_value='0x1000000'), patch('builtins.input', return_value='no'):
            with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
                workflow.unlock()
        self.assertFalse(any('flash' in call for call in self.calls))

    def test_already_unlocked_does_not_flash_or_wipe(self):
        workflow.inspect.return_value = {'securestate': 'flashing_unlocked'}
        workflow.unlock()
        self.assertEqual(self.calls, [])

    def test_mismatch_does_not_flash(self):
        workflow.inspect.side_effect = RuntimeError('Wrong SKU')
        with self.assertRaises(RuntimeError):
            workflow.unlock()
        self.assertFalse(any('flash' in call for call in self.calls))

    def test_okay_but_locked_prompts_again_then_verifies_restore(self):
        with patch.object(workflow, 'fastboot_var', side_effect=['0x1000000', 'oem_locked', 'flashing_unlocked']), \
             patch('builtins.input', side_effect=['ERASE AND UNLOCK', '', '']) as ask:
            workflow.unlock()
        self.assertEqual(ask.call_count, 3)
        self.assertEqual(sum('oem' in call for call in self.calls), 2)
        workflow.restore_stock.assert_called_once_with('FIXTURE123')
        self.assertEqual(self.calls[-1], ['fastboot', '-s', 'FIXTURE123', 'reboot'])

    def test_cancel_prompt_restores_original_without_unlock(self):
        with patch.object(workflow, 'fastboot_var', return_value='0x1000000'), \
             patch('builtins.input', side_effect=['ERASE AND UNLOCK', 'cancel']):
            workflow.unlock()
        workflow.restore_stock.assert_called_once()
        self.assertFalse(any('oem' in call for call in self.calls))

    def test_failed_restore_verification_never_reboots_android_as_success(self):
        workflow.restore_stock.return_value = 'oem_locked'
        with patch.object(workflow, 'fastboot_var', side_effect=['0x1000000', 'flashing_unlocked']), \
             patch('builtins.input', side_effect=['ERASE AND UNLOCK', '']):
            with self.assertRaisesRegex(RuntimeError, 'did not persist'):
                workflow.unlock()
        self.assertFalse(any(call[-1] == 'reboot' for call in self.calls))


if __name__ == '__main__':
    unittest.main()
