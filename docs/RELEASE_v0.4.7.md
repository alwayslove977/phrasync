# Phrasync 0.4.7 — Microsoft Store update fixes

This maintenance release fixes defects in the in-app update flow and makes update confirmations and failures clearer.

- Replaced the browser confirmation showing `127.0.0.1` with an accessible, branded Phrasync dialog in English/Italian. Cancel is the safe default; Escape and Not now do not start installation.
- Store installation requests now start on the desktop UI thread, with StoreContext associated with the actual Phrasync window. The asynchronous operation is awaited away from the UI thread so native Store consent remains responsive.
- Correctly interpret numeric WinRT results and distinguish completion, cancellation, pending installation, low battery and Wi-Fi requirements.
- Preserve original native errors and HRESULT codes in Diagnostics instead of discarding them behind a generic message.
- Prevent overlapping installation requests and provide an explicit Open Microsoft Store fallback.
- Local/GitHub builds remain separate: they do not install Store updates over source files. All export improvements from 0.4.6 remain included.

**Updating an older Store build:** use Microsoft Store to install this release. The old in-app updater cannot acquire its own fix before that upgrade. Uninstall/reinstall is not inherently required for this updater issue; keep your saved projects.

**Verification:** 199 automated tests passed. A real Windows STA/owner-window check successfully initialized a real StoreContext without requesting an installation. Complete download/install/restart through the new updater remains to be verified on a later Store-distributed upgrade, such as 0.4.7 to a future 0.4.8. This release does not claim that end-to-end test has already happened.

Still free, with local media processing. Install Windows builds through the [Microsoft Store](https://apps.microsoft.com/detail/9NF9JBG2PKHX). This GitHub release provides source code, not a separate installer; see the [README](https://github.com/jaydemks/phrasync/blob/main/README.md) for local desktop/browser launch instructions.

The matching 0.4.7.0 Store package was submitted for certification on October 18, 2026. The previous Store build remains available until certification and rollout complete.

Full history: [RELEASE_NOTES.md](https://github.com/jaydemks/phrasync/blob/main/RELEASE_NOTES.md).
