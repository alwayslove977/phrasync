from __future__ import annotations

import asyncio
from types import SimpleNamespace

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
    assert asyncio.run(store_updates.check_updates()) == {"available": True, "count": 1}
    assert fake.install_calls == 0
    assert asyncio.run(store_updates.install_updates()) == {"available": True, "state": "completed"}
    assert fake.install_calls == 1


def test_no_update_does_not_start_installation(monkeypatch):
    fake = FakeStore([])
    monkeypatch.setattr(store_updates, "_context", lambda: fake)
    assert asyncio.run(store_updates.install_updates()) == {"available": False, "state": "up-to-date"}
    assert fake.install_calls == 0
