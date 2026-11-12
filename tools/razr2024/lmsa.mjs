// SPDX-License-Identifier: AGPL-3.0-or-later
// Uses the pinned, MIT-licensed MFD client installed by setup.py.
import {readFileSync, writeFileSync} from 'node:fs';
import {loadState, saveState, getLoginUrl, fetchRsaKey, apiRequest, session}
  from '../../.razr-runtime/mfd/mfd-cli.mjs';

const profile = JSON.parse(readFileSync(new URL('./profile.json', import.meta.url)));
loadState();
try {
  if (process.argv[2] === 'prepare') {
    await fetchRsaKey();
    const url = new URL(await getLoginUrl());
    if (url.protocol !== 'https:' || url.hostname !== 'passport-glb.lenovo.com') throw new Error('Unexpected login destination');
    saveState();
    console.log(url.href);
  } else if (process.argv[2] === 'firmware') {
    if (!session.jwt) throw new Error('Sign in with the MFD Login helper first.');
    await fetchRsaKey();
    const response = await apiRequest('/rescueDevice/getNewResource.jhtml', {
      modelName: profile.model, marketName: 'motorola razr 2024', category: 'Phone', matchType: 1,
      params: {simCount: profile.sim_count, fingerPrint: profile.fingerprint, roCarrier: profile.carrier},
    });
    const result = await response.json();
    if (result.code !== '0000') throw new Error('Lenovo lookup failed (code ' + result.code + '). Sign in again if expired.');
    const rom = result.content?.map(x => x.romResource).find(x => x?.name === profile.archive);
    if (!rom?.uri) throw new Error('Lenovo did not return the exact tested firmware. No substitute will be downloaded.');
    const url = new URL(rom.uri);
    if (url.protocol !== 'https:' || url.hostname !== 'rsddownload-secure.lenovo.com') throw new Error('Unexpected firmware host');
    writeFileSync(process.argv[3], JSON.stringify({name: rom.name, url: url.href}), {mode: 0o600});
    saveState();
    console.log('Exact stock firmware located.');
  } else throw new Error('Usage: lmsa.mjs prepare | firmware OUTPUT_JSON');
} catch (error) {
  // Do not echo raw API bodies, callback URIs or signed download URLs.
  console.error(error.message);
  process.exitCode = 1;
}
