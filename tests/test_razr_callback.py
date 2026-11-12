# SPDX-License-Identifier: AGPL-3.0-or-later
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('callback', pathlib.Path(__file__).parents[1] / 'tools/razr2024/callback.py')
callback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(callback)


class CallbackTests(unittest.TestCase):
    def test_valid_callback_formats(self):
        for host in ['callback', 'authcallback']:
            uri = f'softwareFix://{host}?Authorization=' + 'a' * 32
            self.assertEqual(callback.parse_callback(uri, 100, 101), uri)

    def test_errors_and_unsafe_callbacks(self):
        for uri in ['https://callback?Authorization=x',
                    'softwarefix://evil?Authorization=x',
                    'softwarefix://callback?Authorization=x&token=y',
                    'softwarefix://callback?Authorization=',
                    'softwarefix://callback?error=oauth2+state+not+found',
                    'softwarefix://callback?error=secret-value&Authorization=x']:
            with self.subTest(uri=uri), self.assertRaises(ValueError) as raised:
                callback.parse_callback(uri, 100, 101)
            self.assertNotIn('secret-value', str(raised.exception))

    def test_expired_callback(self):
        with self.assertRaises(ValueError):
            callback.parse_callback('softwarefix://callback?Authorization=x', 100, 701)

    def test_normalized_server_error(self):
        for error in ['oauth2%2520state%2520not%2520found', 'oauth2+state+not+found.']:
            with self.assertRaisesRegex(ValueError, 'oauth2 state not found'):
                callback.parse_callback('softwarefix://callback?error=' + error, 100, 101)
        with self.assertRaises(ValueError) as raised:
            callback.parse_callback('softwarefix://callback?error=oauth2+token+' + 'a' * 32, 100, 101)
        self.assertNotIn('a' * 32, str(raised.exception))
        self.assertIn('[redacted]', str(raised.exception))

    def test_validation_and_secret_cleanup(self):
        for code in [0, 1]:
            with tempfile.TemporaryDirectory() as directory:
                auth = pathlib.Path(directory)
                (auth / 'armed').touch()
                secret = 'a' * 32
                (auth / 'callback.txt').write_text('softwarefix://callback?Authorization=' + secret)
                with patch.object(callback, 'AUTH', auth), patch.object(callback, 'node_executable', return_value='node'), patch.object(callback.subprocess, 'run') as run:
                    run.return_value = SimpleNamespace(returncode=code, stdout='', stderr='')
                    callback.main()
                result = json.loads((auth / 'result.json').read_text())
                self.assertEqual(result['success'], code == 0)
                self.assertNotIn(secret, json.dumps(result))
                self.assertEqual((auth / 'callback.txt').read_text(), '')
                self.assertFalse((auth / 'armed').exists())
                self.assertTrue(run.call_args.kwargs['input'].endswith(secret))

    def test_server_error_never_validates_a_token(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = pathlib.Path(directory)
            (auth / 'armed').touch()
            (auth / 'callback.txt').write_text('softwarefix://callback?error=oauth2+state+not+found')
            with patch.object(callback, 'AUTH', auth), patch.object(callback, 'node_executable', return_value='node'), patch.object(callback.subprocess, 'run') as run:
                callback.main()
                run.assert_not_called()
            result = json.loads((auth / 'result.json').read_text())
            self.assertIn('oauth2 state not found', result['message'])
            self.assertFalse(result['success'])
            self.assertEqual((auth / 'callback.txt').read_text(), '')

    def test_duplicate_success_preserves_session_result(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = pathlib.Path(directory)
            (auth / 'armed').touch()
            uri = 'softwarefix://callback?Authorization=' + 'a' * 32
            with patch.object(callback, 'AUTH', auth), patch.object(callback, 'node_executable', return_value='node'), patch.object(callback.subprocess, 'run') as run:
                run.return_value = SimpleNamespace(returncode=0, stdout='', stderr='')
                for incoming in [uri, uri, 'softwarefix://callback?error=oauth2+state+not+found']:
                    (auth / 'callback.txt').write_text(incoming)
                    callback.main()
                run.assert_called_once()
            self.assertTrue(json.loads((auth / 'result.json').read_text())['success'])
            self.assertEqual((auth / 'callback.txt').read_text(), '')


if __name__ == '__main__':
    unittest.main()
