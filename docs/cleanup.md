# Reversible cleanup

The guide runs `adb shell pm disable-user --user 0 PACKAGE` only for explicitly
selected packages below. It does not uninstall packages or erase their data.
Restore uses `pm enable --user 0 PACKAGE`; this restores enabled behavior, not
every previous internal Package Manager flag. See [Android's ADB reference](https://developer.android.com/tools/adb).

| Package | Shown as | Effect / tradeoff |
|---|---|---|
| `com.dti.tracfone` | Tracfone app installer | Stops this sponsored-app installer; previously installed apps remain |
| `com.dti.motorola` | Mobile Services Manager | Stops this app distribution/recommendation service |
| `com.aura.oobe.motorola` | MotoApps recommendations | Stops this advertising/app recommendation component |
| `com.facebook.appmanager` | Meta App Manager (optional) | Removes this background Meta update path |
| `com.facebook.services` | Meta Services (optional) | Related Facebook integration may change; skip if needed |
| `com.facebook.system` | Meta App Installer (optional) | Stops this installation helper; Facebook itself is not selected |

Package IDs and classifications were checked against the
[Universal Android Debloater Next Generation package database](https://github.com/Universal-Debloater-Alliance/universal-android-debloater-next-generation/blob/main/resources/assets/uad_lists.json)
on November 11, 2026. Descriptions here are original summaries. This is a small
selection, not an imported/automatically updated removal database. Those source
recommendations do not prove behavior on every firmware. The new cleanup runner
has simulated-response tests but no recorded hardware cleanup yet.

Only enabled packages are offered. Nothing outside these six IDs can be disabled
by this tool, even through its internal cleanup function. It leaves telephony,
SMS/MMS, emergency services, IMS, SIM activation, provisioning, account protection,
OTA, the home launcher and Google services outside the selection. Other
preinstalled apps may remain; this is not a replacement of Motorola's UI.

After cleanup, check calls, messaging, notifications and your usual apps. If
something behaves differently, choose **Restore cleanup**. Carrier/system updates
may reinstall or re-enable an app; review the list again afterward.

## How undo works

Before each disable command, the tool atomically saves a local record keyed by a
hash of the phone's serial. It records only listed packages that were enabled
before the operation, then checks Android's disabled package list. Undo applies
only to that phone's recorded packages and verifies each enable. An interruption
leaves a pending entry so undo remains available. Failed verification stops further
changes and keeps the journal for retry.

Keep `.clean-phone/` private and backed up. It is not encrypted; a hashed serial
is not a guarantee of anonymity. It is excluded from Git. Resetting the phone or
deleting this folder loses the relationship to earlier changes. If an update
removes a recorded package, automatic restore may stop at that entry; use the
individual commands for other recorded packages, or get help before editing the journal.

If you lose the journal, boot Android and authorize ADB, then re-enable only apps
you previously disabled. For example:

```sh
adb shell pm enable --user 0 com.dti.tracfone
adb shell pm list packages -e --user 0 com.dti.tracfone
```

Connect only your intended phone for this manual command. Substitute only an ID
you actually disabled. A device policy can refuse a change; the guide does not
bypass it. Work and guest profiles are not supported for cleanup.
