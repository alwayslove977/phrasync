# Phrasync 0.4.9 verification

GitHub source release v0.4.9 is public. Store package 0.4.9.0 was submitted on
22 October 2026 as Submission 13, ID 1152921505702206658. Partner Center confirmed
"In certification", with pre-processing in progress and automatic publication
after approval. This is submission confirmation, not an approval claim.

The uploaded MSIX is 1,527,152,914 bytes. SHA256:
`E60A26C9BC4A9BE79C9B6BFF97153F7CF197CBE5D6E7E8509A03BC662C4E73D4`.
Partner Center validated 0.4.9.0 X64 before submission and replaced 0.4.8.0 in
the draft because the new package supports the same customers. Public patch
notes, the description and certification testing instructions were updated.
Publishing remains automatic after approval; pricing and existing media were
not changed.

## Real Store reproduction, 22 October 2026

The installed Store package was 0.4.7.0. A real check found one update.
Invoking its install endpoint and accepting Microsoft's native consent returned
overall Completed, but the package status was OtherError. Windows still had
0.4.7.0 registered. This reproduced the user's false restart/success report.

Microsoft-Windows-Store/Operational recorded product 9NF9JBG2PKHX failing during
DownloadingProduct with HRESULT 0x80244007 at 15:55:37 local time. No package was
downloaded or staged. This was not a stale version label or an app-in-use error.

Retrying from Phrasync's Microsoft Store product page succeeded at 16:00:58.
Get-AppxPackage then confirmed 0.4.8.0, Status Ok. No uninstall, data reset,
service reset, cache removal or publication was performed.

## Local changes

Validate individual package and Store queue statuses, not just OverallState.
Read and log queue HRESULTs. Refresh the Store query and retry once only for
the observed 0x80244007 download fault. Never retry cancellation automatically.
Persistent failures remain failures and offer the official Store fallback.

Expose actual Store progress through a loopback-only polling endpoint. Show
indeterminate progress when no percentage is available. Add a startup update
notification that waits for existing dialogs and requires explicit consent.
Record update attempts and verify package identity after relaunch. Do not claim
an unchanged package was updated. Register frozen desktop EXEs for Windows-managed
restart during patching, never a source Python interpreter or an old MSIX path.
Add space above and below the welcome dialog's Buy me a coffee button.

## Verification limits

Full isolated regression suite: 246 tests passed. No tracked whitespace errors
were reported by git diff --check.

The compiled 0.4.9 executable started successfully in an isolated workspace on
port 5559. Its update UI, translations, HTML and CSS matched source hashes.
Update status and progress endpoints responded correctly. Source-install and
cross-origin guards rejected installation requests as expected. The native STA
smoke test also verified real StoreContext owner initialization against a real
WinForms HWND without downloading or installing an update.

Automated Python and JavaScript tests cover progress, consent, cancellation,
duplicate prevention, false overall completion, queue errors, bounded retry,
post-restart identity verification and source/Store separation. Tests use an
isolated workspace, not the user's projects.

The 0.4.9 source desktop window was opened on port 5549 with isolated test data.
The browser verification connection failed because its installed runtime could
not find browser-service.mjs. No successful visual screenshot inspection is
claimed. The spacing change still needs the user's visual check.

The real successful upgrade was performed by the existing Microsoft Store app,
not by the new 0.4.9 code. The new automatic retry and Windows-managed
restart require a future signed Store update for full end-to-end validation.
Do not describe them as proven against Store distribution yet. A persistent
Microsoft/Windows Update download failure cannot be guaranteed away by app code.
