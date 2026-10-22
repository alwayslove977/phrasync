# Phrasync 0.4.9

This maintenance release makes Microsoft Store updates clearer and more reliable. It addresses a real case where the Store returned an overall completion result even though the individual package had failed to download, leaving Phrasync on the previous version.

## Accurate update results

Phrasync now checks individual package results and the Store installation queue before reporting completion. Download and installation errors retain their original codes in Diagnostics. An incomplete or failed update no longer produces a misleading success message asking you to restart.

For the observed Windows Update download fault 0x80244007, Phrasync refreshes the update request and retries once. Cancellation is never retried automatically. Persistent failures still provide an explicit Microsoft Store fallback rather than an endless retry loop.

## Progress and restart handling

Settings shows the progress reported by Microsoft Store, with an indeterminate indicator while a percentage is unavailable. A startup notification lets you review available updates after dismissing any existing welcome dialog. Installation still requires your permission; the startup check does not install anything automatically.

Update attempts are recorded locally so the next launch can verify whether a newer package is actually running. The packaged Windows app also registers for Windows-managed restart during updating, without trying to relaunch an obsolete installation path. Source checkouts never register the Python interpreter for restart or install Store updates over your source files.

## Welcome dialog

The optional Buy me a coffee button has more space above and below it. Existing projects, media, editing tools and export features are unchanged.

## Verification and availability

246 automated Windows tests passed, including update consent, cancellation, duplicate prevention, progress, package failures, bounded retry and verification after relaunch. The original failure was reproduced on the real 0.4.7 Store installation, and updating that installation to 0.4.8 through Microsoft Store succeeded without uninstalling or resetting app data.

The new 0.4.9 retry and restart flow still requires confirmation through a subsequent real Store upgrade. App code cannot guarantee recovery from every Microsoft Store or Windows Update service error.

[GitHub v0.4.9](https://github.com/jaydemks/phrasync/releases/tag/v0.4.9) provides the source release. The [Microsoft Store](https://apps.microsoft.com/detail/9NF9JBG2PKHX) is the Windows installer channel. The matching 0.4.9.0 package becomes available after certification and rollout; the previous approved release remains available in the meantime. If your older in-app updater cannot install this release, update through Microsoft Store directly. No routine uninstall is required for this updater fix.

Phrasync remains free and open source, with local media processing. Full history is in [RELEASE_NOTES.md](https://github.com/jaydemks/phrasync/blob/main/RELEASE_NOTES.md).
