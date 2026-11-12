# Start here

Use a phone you own or are authorized to service. This is a source-based preview,
not a signed installer. No separate unlock app is needed; Python and Android USB
tools are prerequisites. Read the source before running it.

## 1. Prepare the computer

All hosts need **Python 3.11+** and **Android Platform Tools**. Only unlocking needs
**Git**, **Node.js 22+**, an internet connection and about **12 GB free disk space**.
Lenovo firmware download may require your own Lenovo account. Cleanup works
offline after prerequisites are installed.

### macOS

If you already use Homebrew:

```sh
brew install python node git
brew install --cask android-platform-tools
xcode-select --install
```

Xcode Command Line Tools compile the local login helper for unlocking; skip their
installation if already present. Alternatively install
[Python](https://www.python.org/downloads/), [Node.js](https://nodejs.org/en/download),
[Git](https://git-scm.com/downloads), and
[Google's Platform Tools](https://developer.android.com/tools/releases/platform-tools)
directly, and add their executable folders to your PATH.

Extract the repository ZIP, open Terminal in that folder, and run
`python3 clean_phone.py`. `Start.command` is a convenience shortcut. If macOS
blocks a downloaded shortcut, use the terminal command after inspecting the
source; the workflow does not disable Gatekeeper. Do not run it with `sudo`.

### Windows

1. Install [Python 3.11+](https://www.python.org/downloads/windows/),
   [Node.js 22+](https://nodejs.org/en/download) and [Git](https://git-scm.com/downloads/win).
   Node and Git are optional for cleanup only. Enable Python's PATH option.
2. Download [Google's Windows Platform Tools ZIP](https://developer.android.com/tools/releases/platform-tools),
   extract it, and add the `platform-tools` folder to your user PATH. Reopen your terminal.
3. Install/refresh [Motorola USB drivers](https://en-us.support.motorola.com/app/usb-drivers)
   if Windows does not recognize the phone. ADB and Fastboot may need different
   driver bindings; verify both before unlocking.
4. Extract this repository ZIP. Double-click `Start.bat`, or open a terminal there
   and run `py -3 clean_phone.py`. If `py` is unavailable use
   `python clean_phone.py`. Do not run inside the ZIP viewer.

Windows source checks run in CI. Live Windows USB and Lenovo login have not been
validated by this fork's recorded hardware run.

### Linux

Install Python 3.11+, its `venv` support, Git, Node.js 22+, `adb` and `fastboot`
through your distribution or the official downloads above. Confirm versions;
older distro Node packages may not meet the requirement. On Debian/Ubuntu,
`python3-venv`, `adb`, `fastboot` and `android-sdk-platform-tools-common` are the
relevant package names. Follow Google's
[USB permission instructions](https://developer.android.com/studio/run/device)
for `plugdev`/udev if needed; sign out and back in after group changes.

Run `python3 clean_phone.py` from the extracted repository. Do not run the whole
tool as root to work around USB permissions. Linux source checks run in CI;
live Linux USB and Lenovo login have not been validated here.

### Check prerequisites

```sh
python3 --version   # Windows: py -3 --version
adb version
fastboot --version  # unlock/recovery only
node --version     # unlock setup only; 22+
git --version      # unlock setup only
```

## 2. Prepare the phone and check it

1. Back up photos, messages, authenticator accounts and anything else you need
   before considering unlock. It is a factory reset. Charge to at least 50%.
2. Finish Android setup. In Settings → About phone, tap **Build number** seven
   times; in Developer options enable **USB debugging**.
3. Connect one phone with a reliable data cable. Unlock its screen and accept
   **Allow USB debugging** for your own computer.
4. Start the launcher and choose **1**. Or use `python3 clean_phone.py --check`
   (`py -3` on Windows) for the same read-only identity check.

No matching unlock profile means **stop the unlock path**. Cleanup is independent
and may still work. Do not downgrade or flash another phone's image to get a match.

## 3. Choose your path

### Cleanup only: option 3

This requires Android running on a Motorola MediaTek phone, the owner user, and
completed setup. It shows only currently enabled apps in the reviewed list.
Read each effect, enter the desired numbers, then type `DISABLE`. Enter alone
cancels. Each change is verified and recorded for undo. See [cleanup details](cleanup.md).

### Unlock, then cleanup: option 2, then option 3

Only **XT2453V / aito / W1UCS36H.96-35-12-5 / matching MBM / slot A** is supported.
Read the [full runbook and recovery notes](razr2024-xt2453v.md) first.

1. The launcher checks the reported model/build. Type `PREPARE` to install pinned
   local dependencies. This consent does not authorize a flash.
2. Provide your exact original stock ZIP, or press Enter for Lenovo lookup/download.
   Archives must match the recorded SHA-256; a matching filename is insufficient.
3. **Mac login:** MFD Login opens. Start a fresh login, complete it in your browser,
   wait for **Login successful**, then press Enter. **Windows/Linux login:** follow
   the pinned downloader's browser/callback instructions. If no URL handler exists,
   browser developer tools can expose the `callback.jhtml` response's Authorization
   value; paste it only into your local downloader prompt. Never reuse a consumed
   authorization code or success page. If login fails, use a legitimately obtained
   exact stock ZIP. Live CLI login is unverified on Windows/Linux.
4. Preparation checks the archive, original LK, patch and five signed subimages.
   Software checks do not prove compatibility with an untested phone.
5. The phone enters Fastboot. The runner checks its exact SKU, MBM, product,
   active slot and bootloader mode before asking for **`ERASE AND UNLOCK`**.
6. Hold the phone before continuing. On the tested Razr, **Volume Down selects
   Yes; Volume Up confirms** within 30 seconds. The runner checks lock state even
   when the command says `OKAY`. If still locked it offers a retry.
7. It restores the exact original LK, verifies that unlock persisted, and boots
   Android. Complete setup, re-enable/authorize USB debugging, and choose **3**
   for cleanup. It never automatically disables apps after the reset.

An already-unlocked phone does not need another unlock. If an earlier attempt was
interrupted before restoring stock LK, read recovery and use option **5**.
Unlocking may affect apps that check device integrity; test the apps you need.

## 4. Undo or recover

- **Undo cleanup:** reconnect/authorize the same phone in Android and choose **4**.
  Review the list and type `RESTORE`. Apps disabled before this tool are left alone.
- **Interrupted cleanup:** the journal is saved before each mutation. Choose **4**
  to undo even if an interruption prevented the final result from being recorded.
- **Interrupted unlock:** keep `.razr-work` and the stock archive. If the exact phone
  is in Fastboot, option **5** validates and restores stock LK after `RESTORE STOCK`.
  It does not relock or restore erased user data. If the phone does not enumerate,
  read the [recovery limits](razr2024-xt2453v.md#recovery--interruption) and stop blind writes.

Keep the same checkout and its ignored work folders; a fresh download has no
previous undo/recovery files. On Windows use a private user-owned folder; local
files inherit that account's ACLs. The Lenovo client saves its session in
`~/.mfd-cli-state.json`; do not share it. Disable USB debugging when finished.
The tool sends no analytics or reports to this fork; dependency and Lenovo
login/download requests contact their providers.

## Troubleshooting

| Symptom | Action |
|---|---|
| No phone found | Unlock screen, authorize USB debugging, use a data cable, check drivers/USB permissions |
| More than one phone | Disconnect the others; the guide deliberately does not guess |
| Wrong model/build/slot | Unlock is unsupported; do not change the profile or hashes |
| No cleanup candidates | Listed apps are absent or already disabled; no broad removal is attempted |
| Android refuses a disable | Do not force it; Restore cleanup can undo partial work |
| Lenovo login expired | Start a fresh login or use the exact local ZIP |
| Firmware hash mismatch | Obtain the exact package; no older/newer substitute |
| Operation lock error | Close the other operation normally; retry after it exits |
| Undo journal lost | See the individual `pm enable` command in [cleanup details](cleanup.md) |

Do not post raw logs, `.razr-work`, `.clean-phone`, tokens, serials or IMEIs in
GitHub issues. Use the compatibility template for a limited, reviewed summary.
