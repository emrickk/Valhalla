# Valhalla Clean Phone

**A guided starting point for Straight Talk / Tracfone Motorola MediaTek owners.**
Check your phone, unlock a verified model/build if you choose, and disable selected
carrier app installers and optional Meta helpers—with an undo option.

[![Source checks](https://github.com/emrickk/Valhalla/actions/workflows/razr-checks.yml/badge.svg?branch=main)](https://github.com/emrickk/Valhalla/actions/workflows/razr-checks.yml)

**[Start here: setup and walkthrough →](docs/getting-started.md)** ·
**[Download the source ZIP](https://github.com/emrickk/Valhalla/archive/refs/heads/main.zip)** ·
[Compatibility and hardware evidence](docs/razr2024-xt2453v.md)

## What this can do today

| Step | What happens | Current boundary |
|---|---|---|
| Check | Reads model, build, chipset and mode | No flash, wipe or app changes |
| Unlock (optional) | Finds exact stock firmware, validates hashes, guides confirmation, restores stock LK and verifies unlock | **Razr 2024 XT2453V, Android 16, W1UCS36H.96-35-12-5, slot A only** |
| Cleanup | Shows each supported app and its effect; disables only your selection | Motorola MTK, Android owner profile, six reviewed optional packages; apps must be present |
| Undo | Re-enables packages recorded by this tool for this phone | Keep the local `.clean-phone` folder |

**Unlocking erases all phone data and can brick the device.** Back up first.
Cleanup alone does **not** require unlocking, root, or a factory reset.
This keeps Motorola's Android and launcher. It does not install a new ROM, remove
a SIM/network lock, grant root, or remove Google account verification.

## Run one launcher

Install [Python 3.11+](https://www.python.org/downloads/) and Google's
[Android Platform Tools](https://developer.android.com/tools/releases/platform-tools),
then follow your computer's [setup steps](docs/getting-started.md).

```sh
git clone https://github.com/emrickk/Valhalla.git
cd Valhalla
python3 clean_phone.py
```

On **Windows**, run `py -3 clean_phone.py` or double-click `Start.bat`.
On **macOS**, run the command above or double-click `Start.command`.
On **Linux**, run the command above. A source ZIP works too; extract it first.
The launcher explains missing prerequisites. Unlock setup also needs Git, Node.js
22+, and, on Mac, Xcode Command Line Tools. It installs pinned Python dependencies
and the firmware client inside this checkout; you do not need another unlock app.

```text
1 Check phone (read only)
2 Guided unlock (factory reset)
3 Review and disable optional apps
4 Restore cleanup
5 Restore exact stock LK (recovery)
0 Exit
```

Start with **1**. Use **3** if you only want cleanup. Use **2** only after reading
the backup, compatibility and recovery notes. After an unlock, complete Android
setup and authorize USB debugging again before returning for cleanup.

## Honest compatibility status

- **One underlying hardware unlock verified:** XT2453V on the exact build above,
  using an Apple Silicon Mac. [Recorded procedure and hashes](docs/razr2024-xt2453v.md).
- **Preview automation:** the new guided workflow and cleanup are tested with
  simulated device responses. They have not completed a fresh end-to-end hardware
  run. Source checks cover macOS, Windows and Linux; CI is not a USB/driver test.
- **Other Motorola MTK phones:** cleanup may be offered when the phone passes its
  checks. Unlocking stops until an independently verified model/build profile is
  added. A shared chipset or brand is not proof of LK compatibility.
- **Windows/Linux firmware login:** the integrated upstream browser/callback CLI
  is available, but its live login and USB flow are unverified here. The exact local
  firmware ZIP is an alternative. Mac uses the verified native callback approach.

## Cleanup, recovery and privacy

The initial cleanup list covers Tracfone's installer, Mobile Services Manager,
MotoApps recommendations and three optional Meta background helpers. It leaves
the phone/SMS stack, launcher, updates, Google services and setup components alone.
See the [exact list and effects](docs/cleanup.md); review every selection.

Keep `.razr-work/` for unlock recovery and `.clean-phone/` for undo. Neither is
published. Do not upload firmware, login tokens, device IDs or these folders to an
issue. [Recovery instructions](docs/razr2024-xt2453v.md#recovery--interruption).

Want another model supported? Use the
[compatibility request](https://github.com/emrickk/Valhalla/issues/new?template=compatibility.yml)
and share only model/build/chipset information—not a serial or IMEI. Do not edit
the existing profile to force your phone through.

## Credits and development

This is **emrickk's community fork**, not an official Motorola/Lenovo product.
The unlock work builds on [Valhalla](https://github.com/crabcakes97/Valhalla), its
bundled Val Protocol, and the pinned
[Moto Firmware Downloader](https://github.com/JoshRob297/moto-firmware-downloader).
Original credits and licenses remain in their files. New guided-tool code is
AGPL-3.0-or-later; see [its license](tools/razr2024/LICENSE).
Cleanup package choices are documented with [source attribution](docs/cleanup.md).

```sh
python3 -m unittest discover -s tests -v
python3 clean_phone.py --about
```

The legacy `Valhalla.py` GUI remains available for research users with its
[historical instructions](docs/legacy-valhalla.md). Its broader compatibility
claims are **not** verified profiles for the guided launcher. New users should
start with `clean_phone.py`.
