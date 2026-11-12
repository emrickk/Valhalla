# SPDX-License-Identifier: AGPL-3.0-or-later
"""Accept an armed macOS login callback and validate it with MFD locally."""
import json
import hashlib
import pathlib
import re
import subprocess
import time
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUTH = ROOT / '.razr-work/auth'


def parse_callback(uri, armed_at, now):
    parsed = urllib.parse.urlsplit(uri)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    values = [v for k, vs in params.items()
              if k.lower() in {'authorization', 'auth', 'token'} for v in vs]
    if not (
        0 <= now - armed_at <= 600
        and len(uri) <= 16384
        and parsed.scheme.lower() == 'softwarefix'
        and parsed.netloc.lower() in {'callback', 'authcallback'}
        and parsed.path in {'', '/'}
        and not parsed.fragment
    ):
        raise ValueError('Invalid or expired login callback. Start a fresh login.')
    errors = [v for k, vs in params.items() if k.lower() == 'error' for v in vs]
    if errors:
        # Never copy arbitrary callback contents (which can contain credentials) into diagnostics.
        known = {'oauth2 state not found', 'oauth2 token error', 'access_denied',
                 'oauth2 code error', 'oauth2 user error', 'oauth2 login error',
                 'oauth2 state error', 'oauth2 code not found'}
        error = urllib.parse.unquote(errors[0]).lower().strip(' .')
        reason = error if error in known else 'authorization failed'
        # Keep a bounded diagnostic vocabulary, never arbitrary callback data.
        words = error.replace('_', ' ').replace(':', ' ').split()
        allowed = set('oauth2 state token code user login error invalid expired not found null access denied failed success request account email empty is the no response from server'.split())
        if words and len(words) <= 12 and all(word in allowed for word in words):
            reason = ' '.join(words)
        if error.startswith('oauth2 ') and len(error) <= 160:
            reason = re.sub(r'[\w@./+=-]{16,}', '[redacted]', error)
        raise ValueError('Lenovo returned: ' + reason + '. Start a fresh login; do not reuse the success page.')
    if len(values) != 1 or not values[0]:
        raise ValueError('The callback contains no unique session token. Start a fresh login.')
    return uri


def node_executable():
    return json.loads((ROOT / '.razr-runtime/config.json').read_text())['node']


def main():
    callback = AUTH / 'callback.txt'
    result = {'success': False}
    try:
        armed = AUTH / 'armed'
        uri = callback.read_text().strip()
        digest = hashlib.sha256(uri.encode()).hexdigest()
        result_file = AUTH / 'result.json'
        if result_file.exists():
            previous = json.loads(result_file.read_text())
            if previous.get('success') and (not armed.exists() or previous.get('callback_sha256') == digest):
                result = previous
                print(result['message'])
                return
        result['callback_sha256'] = digest
        parsed = urllib.parse.urlsplit(uri)
        armed_at = armed.stat().st_mtime
        result['callback_shape'] = {
            'scheme': parsed.scheme, 'host': parsed.netloc,
            'parameter_names': list(urllib.parse.parse_qs(parsed.query)),
            'age_seconds': round(time.time() - armed_at), 'length': len(uri)}
        parse_callback(uri, armed_at, time.time())
        armed.unlink()
        completed = subprocess.run(
            [node_executable(), str(ROOT / '.razr-runtime/mfd/mfd-cli.mjs'),
             'login', '--stdin'], input=uri, text=True, capture_output=True, timeout=90)
        result.update(success=completed.returncode == 0, exit_code=completed.returncode)
        result['diagnostic_flags'] = [msg for msg in
            ['Invalid token', 'Could not extract', 'Backend Validation Failed',
             'Login successful', 'AUTH_EXPIRED', 'Fingerprint expired']
            if msg in completed.stdout + completed.stderr]
        result['message'] = ('Login successful. Lenovo verified the session and it was saved.'
                             if result['success'] else
                             'The callback arrived, but session validation failed. Start a fresh login.')
    except Exception as exc:
        result.update(success=False, error_type=type(exc).__name__)
        result['message'] = (str(exc) if isinstance(exc, ValueError) else
                             'No active login attempt, or the helper could not finish. Start a fresh login.')
    finally:
        callback.write_text('')
        (AUTH / 'result.json').write_text(json.dumps(result))
    print(result['message'])


if __name__ == '__main__':
    main()
