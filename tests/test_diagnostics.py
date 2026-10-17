from __future__ import annotations

from fastapi.testclient import TestClient

import app as app_module
from phrasync import diagnostics


def test_editor_document_and_assets_are_versioned_for_in_place_updates():
    response = TestClient(app_module.app).get("/?desktop=1&app_version=0.4.4")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    from phrasync.config import APP_VERSION
    for asset in ['app.js', 'app-render.js', 'diagnostics.js', 'styles.css']:
        assert f'/static/{asset}?v={APP_VERSION}' in response.text
    assert response.text.index("diagnostics.js?v=") < response.text.index("app.js?v=")


def test_support_report_redacts_home_and_tokens(tmp_path, monkeypatch):
    log = tmp_path / "phrasync.log"
    log.write_text("Error at C:/Users/Example/song.mp4 with hf_1234567890secret\n", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "LOG_FILE", log)
    monkeypatch.setattr(diagnostics, "system_summary", lambda: {"Phrasync": "0.4.3", "GPU": "Test GPU"})
    monkeypatch.setattr(diagnostics.Path, "home", lambda: diagnostics.Path("C:/Users/Example"))
    report = diagnostics.support_report()
    assert "Phrasync: 0.4.3" in report
    assert "GPU: Test GPU" in report
    assert "<USER_HOME>" in report
    assert "C:/Users/Example" not in report
    assert "hf_1234567890secret" not in report


def test_local_diagnostics_can_be_read_and_frontend_error_recorded(monkeypatch):
    events = []
    monkeypatch.setattr(app_module, "_require_local_request", lambda request: None)
    monkeypatch.setattr(app_module, "support_report", lambda: "Phrasync support report\nGPU: Test GPU")
    monkeypatch.setattr(app_module, "log_event", lambda *args: events.append(args))
    client = TestClient(app_module.app)
    report = client.get("/api/diagnostics")
    assert report.status_code == 200
    assert report.headers["cache-control"] == "no-store"
    assert "GPU: Test GPU" in report.text
    event = client.post("/api/diagnostics/events", json={"level": "error", "category": "javascript", "message": "ReferenceError: test"})
    assert event.json() == {"recorded": True}
    assert events == [("error", "javascript", "ReferenceError: test")]
    assert client.post("/api/diagnostics/events", json={"message": ""}).status_code == 400
