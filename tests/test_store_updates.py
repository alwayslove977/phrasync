from __future__ import annotations

import asyncio
import threading
from enum import IntEnum
from types import SimpleNamespace
import pytest

from fastapi.testclient import TestClient

import app as app_module
from phrasync import store_updates


class FakeStore:
    def __init__(self, updates):
        self.updates = updates
        self.install_calls = 0

    async def get_app_and_optional_store_package_updates_async(self):
        return self.updates

    async def request_download_and_install_store_package_updates_async(self, updates):
        assert updates == self.updates
        self.install_calls += 1
        return SimpleNamespace(overall_state="Completed")


def test_portable_preview_never_calls_store(monkeypatch):
    monkeypatch.setattr(store_updates, "package_identity", lambda: None)
    monkeypatch.setattr(app_module, "_require_local_request", lambda request: None)
    client = TestClient(app_module.app)
    from phrasync.config import APP_VERSION
    assert client.get("/api/store-updates/status").json() == {"version": APP_VERSION, "packaged": False}
    assert client.post("/api/store-updates/check", headers={"Origin": "http://testserver"}).status_code == 503
    assert client.post("/api/store-updates/install", headers={"Origin": "http://testserver"}).status_code == 503
    assert client.post("/api/store-updates/install", headers={"Origin": "https://other.example"}).status_code == 403


def test_store_check_and_install_are_separate_consent_actions(monkeypatch):
    fake = FakeStore([object()])
    monkeypatch.setattr(store_updates, "_context", lambda: fake)
    monkeypatch.setattr(store_updates, "_start_install_on_ui", lambda updates: (fake, fake.request_download_and_install_store_package_updates_async(updates)))
    assert asyncio.run(store_updates.check_updates()) == {"available": True, "count": 1}
    assert fake.install_calls == 0
    assert asyncio.run(store_updates.install_updates()) == {"available": True, "state": "completed"}
    assert fake.install_calls == 1


def test_no_update_does_not_start_installation(monkeypatch):
    fake = FakeStore([])
    monkeypatch.setattr(store_updates, "_context", lambda: fake)
    assert asyncio.run(store_updates.install_updates()) == {"available": False, "state": "up-to-date"}
    assert fake.install_calls == 0


@pytest.mark.parametrize("code,name", list(store_updates.STATES.items()))
def test_winrt_numeric_and_named_enum_states(code, name):
    state = IntEnum('State', {'VALUE':code})(code)
    assert store_updates._state_name(state) == name
    assert store_updates._state_name(code) == name
    assert store_updates._state_name('StorePackageUpdateState.COMPLETED') == 'completed'
    assert store_updates._state_name('ERROR_WIFI_REQUIRED') == 'wifi-required'


def test_install_binds_owner_before_initiating_on_ui(monkeypatch):
    calls = []
    class Native:
        IsDisposed = False
        IsHandleCreated = True
        InvokeRequired = True
        Handle = SimpleNamespace(ToInt64=lambda: 12345)
        def Invoke(self, callback):
            calls.append('ui')
            callback()
    sentinel = object()
    fake = SimpleNamespace(request_download_and_install_store_package_updates_async=lambda updates: calls.append(('request',updates)) or sentinel)
    monkeypatch.setattr(store_updates, '_window', SimpleNamespace(native=Native()))
    monkeypatch.setattr(store_updates, '_context', lambda: calls.append('context') or fake)
    monkeypatch.setattr(store_updates, '_ui_delegate', lambda callback: callback)
    monkeypatch.setattr(store_updates, '_initialize_owner', lambda context, hwnd: calls.append(('owner',context,hwnd)))
    assert store_updates._start_install_on_ui(['update']) == (fake,sentinel)
    assert calls == ['ui','context',('owner',fake,12345),('request',['update'])]


def test_install_with_unavailable_window_fails_safely(monkeypatch):
    monkeypatch.setattr(store_updates, '_window', None)
    with pytest.raises(store_updates.StoreUpdateUnavailable,match='window is not ready'):
        store_updates._start_install_on_ui(['update'])


def test_store_hresult_is_logged_and_returned_and_lock_is_released(monkeypatch):
    fake = FakeStore([object()])
    monkeypatch.setattr(store_updates,'_context',lambda:fake)
    def broken(_):
        error = OSError('Invalid window handle')
        error.winerror = -2147023496
        raise error
    events=[]
    monkeypatch.setattr(store_updates,'_start_install_on_ui',broken)
    monkeypatch.setattr(store_updates,'log_event',lambda *args: events.append(args))
    with pytest.raises(store_updates.StoreUpdateUnavailable,match='0x80070578'):
        asyncio.run(store_updates.install_updates())
    assert any('Invalid window handle' in event[2] for event in events)
    assert not store_updates._install_lock.locked()


def test_duplicate_install_requests_are_rejected(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    fake=FakeStore([object()])
    monkeypatch.setattr(store_updates,'_context',lambda:fake)
    async def finish():
        await asyncio.to_thread(release.wait,5)
        return SimpleNamespace(overall_state=3)
    def start(_):
        entered.set()
        return fake,finish()
    monkeypatch.setattr(store_updates,'_start_install_on_ui',start)
    async def run():
        first=asyncio.create_task(store_updates.install_updates())
        await asyncio.to_thread(entered.wait,5)
        try:
            with pytest.raises(store_updates.StoreUpdateUnavailable,match='already in progress'):
                await store_updates.install_updates()
        finally:
            release.set()
        assert (await first)['state']=='completed'
    asyncio.run(run())


def test_local_build_cannot_open_store_install_flow(monkeypatch):
    monkeypatch.setattr(store_updates,'package_identity',lambda:None)
    with pytest.raises(RuntimeError,match='Store installation'):
        app_module.desktop_export.open_store_updates()


def test_store_confirmation_is_branded_dialog_not_browser_confirm():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    script=(root/'static/store-updates.js').read_text(encoding='utf8')
    html=(root/'static/index.html').read_text(encoding='utf8')
    assert 'confirm(' not in script
    assert 'dialog.showModal()' in script
    assert 'if (!await confirmInstall()) return;' in script
    assert 'id="storeUpdateConfirm"' in html
    assert 'value="cancel" autofocus' in html


def test_update_controller_consent_and_result_flow():
    import shutil
    import subprocess
    from pathlib import Path
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is unavailable')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node,str(root/'tests/store_updates_ui.cjs')],cwd=root,capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
