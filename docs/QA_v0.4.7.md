# 0.4.7 update-flow candidate — October 18, 2026

Local only. No GitHub push, tag, release, or Microsoft Store submission.

## Findings

The installed 0.4.5 log confirms successful update discovery followed by a generic 503 from Phrasync's install endpoint. The original native exception was discarded, so its actual HRESULT cannot be recovered from that log. Code inspection found that installation was initiated on the HTTP event-loop thread and StoreContext was not associated with the desktop HWND. Microsoft requires UI-thread initiation and an owner window for this consent-displaying desktop API.

The old confirmation used browser `confirm()`, which exposed the local origin. Numeric WinRT IntEnum results could also be displayed as numbers instead of meaningful outcomes.

## Changes

- An accessible Phrasync confirmation dialog replaces browser confirmation. Cancel is initially focused; Escape and Not now do not install. English/Italian text is included.
- The real pywebview WinForms owner is registered at startup. Context creation, HWND association and install-operation initiation run on that window's UI thread. The returned operation is awaited off the UI thread; no nested asyncio loop blocks native Store consent.
- Duplicate installation requests are rejected, and UI controls remain guarded during confirmation and installation.
- WinRT result values are mapped explicitly, with different messages for completion, cancellation, battery/network requirements and other errors.
- Native exception details and HRESULT codes are retained in the local support log. Users can explicitly open the fixed Phrasync Microsoft Store listing on failure.
- Portable/GitHub builds remain unable to initiate Store installs. No external installer or second update channel was introduced.

## Verification

- Full regression suite: 199 tests passed, including fake-network UI consent/result tests and backend state/ownership/concurrency/error tests.
- `scripts/qa_updates_047.py` verified real Windows STA dispatch and successfully initialized a real StoreContext with a real HWND. The install call itself was synthetic: no Store download or installation was requested.
- A fresh standalone Windows candidate is built under `release/v0.4.7/dist/Phrasync` for local inspection.

## Remaining release verification

A complete real Store update has not been performed with this candidate. Verify the native consent, download, install/restart and final version on a Store-distributed upgrade before calling the installation issue fully resolved. Native code fixes cannot be retroactively applied to the running 0.4.5; its first upgrade to a fixed version must be initiated from Microsoft Store itself. Uninstall/reinstall is not inherently required for this updater defect.

References:

- https://learn.microsoft.com/en-us/uwp/api/windows.services.store.storecontext.requestdownloadandinstallstorepackageupdatesasync
- https://learn.microsoft.com/en-us/uwp/api/windows.services.store.storecontext
- https://pywinrt.readthedocs.io/en/latest/api/runtime.interop.html
