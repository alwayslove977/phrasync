import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import app as app_module
from phrasync import folder_picker as picker


def test_native_picker_preserves_unicode_spaces_and_cancellation(tmp_path, monkeypatch):
    selected = tmp_path / "動画 exports"
    selected.mkdir()
    run = Mock(side_effect=[SimpleNamespace(returncode=0, stdout=json.dumps({"directory": str(selected)})),
                            SimpleNamespace(returncode=0, stdout='{"directory": null}')])
    monkeypatch.setattr(picker, "available", lambda: True)
    monkeypatch.setattr(picker.subprocess, "run", run)
    service = picker.BrowserFolderPicker()
    assert service.selected() is None
    assert service.choose() == str(selected.resolve())
    assert service.choose() is None
    assert service.selected() == str(selected.resolve())
    assert run.call_args.args[0][-1] == str(selected.resolve())
    assert "shell" not in run.call_args.kwargs
    assert "creationflags" in run.call_args.kwargs


@pytest.mark.parametrize("failure", ["unsupported", "failed", "invalid_json", "relative", "missing", "timeout"])
def test_native_picker_errors_leave_state_unchanged_and_release_lock(tmp_path, monkeypatch, failure):
    service = picker.BrowserFolderPicker()
    service._directory = str(tmp_path)
    monkeypatch.setattr(picker, "available", lambda: failure != "unsupported")
    result = SimpleNamespace(returncode=0, stdout='{"directory": null}')
    if failure == "failed": result.returncode = 1
    if failure == "invalid_json": result.stdout = "not JSON"
    if failure == "relative": result.stdout = '{"directory": "relative/folder"}'
    if failure == "missing": result.stdout = json.dumps({"directory": str(tmp_path / "missing")})
    run = Mock(return_value=result)
    if failure == "timeout": run.side_effect = subprocess.TimeoutExpired("picker", 300)
    monkeypatch.setattr(picker.subprocess, "run", run)
    with pytest.raises(picker.FolderPickerUnavailable): service.choose()
    assert service.selected() == str(tmp_path)
    assert not service._dialog_lock.locked()


def test_only_one_native_dialog_can_open(monkeypatch):
    service = picker.BrowserFolderPicker()
    service._dialog_lock.acquire()
    run = Mock()
    monkeypatch.setattr(picker.subprocess, "run", run)
    try:
        with pytest.raises(picker.FolderPickerBusy): service.choose()
        run.assert_not_called()
    finally:
        service._dialog_lock.release()


def test_browser_folder_api_requires_loopback_and_same_origin(monkeypatch, tmp_path):
    choose = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(app_module.desktop_export, "_window", None)
    monkeypatch.setattr(app_module.browser_folder_picker, "choose", choose)
    client = TestClient(app_module.app, base_url="http://localhost", client=("127.0.0.1", 12345))
    assert client.post("/api/export-folder/choose").status_code == 403
    assert client.post("/api/export-folder/choose", headers={"origin": "https://evil.example"}).status_code == 403
    remote = TestClient(app_module.app, client=("192.0.2.10", 12345))
    assert remote.post("/api/export-folder/choose", headers={"origin": "http://testserver"}).status_code == 403
    choose.assert_not_called()
    rebound = TestClient(app_module.app, base_url="http://evil.example", client=("127.0.0.1", 12345))
    assert rebound.post("/api/export-folder/choose", headers={"origin": "http://evil.example"}).status_code == 403
    response = client.post("/api/export-folder/choose", headers={"origin": "http://localhost"})
    assert response.status_code == 200
    assert response.json() == {"directory": str(tmp_path), "cancelled": False}


def test_api_cancel_errors_and_attached_desktop_bridge(monkeypatch, tmp_path):
    client = TestClient(app_module.app, base_url="http://localhost", client=("127.0.0.1", 12345))
    headers = {"origin": "http://localhost"}
    monkeypatch.setattr(app_module.desktop_export, "_window", None)
    choose = Mock(return_value=None)
    monkeypatch.setattr(app_module.browser_folder_picker, "choose", choose)
    response = client.post("/api/export-folder/choose", headers=headers)
    assert response.json() == {"directory": None, "cancelled": True}
    choose.side_effect = picker.FolderPickerBusy("already open")
    assert client.post("/api/export-folder/choose", headers=headers).status_code == 409
    choose.side_effect = picker.FolderPickerUnavailable("manual path")
    assert client.post("/api/export-folder/choose", headers=headers).status_code == 503
    monkeypatch.setattr(app_module.desktop_export, "_window", object())
    desktop_choose = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(app_module.desktop_export, "choose_render_directory", desktop_choose)
    monkeypatch.setattr(app_module.desktop_export, "get_selected_render_directory", lambda: str(tmp_path))
    assert client.get("/api/export-folder").json() == {"available": True, "directory": str(tmp_path)}
    assert client.post("/api/export-folder/choose", headers=headers).json()["directory"] == str(tmp_path)
    desktop_choose.assert_called_once()


def test_frozen_executable_never_attempts_python_helper(monkeypatch):
    monkeypatch.setattr(picker.sys, "frozen", True, raising=False)
    assert picker.available() is False
