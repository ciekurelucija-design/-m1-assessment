"""Neparedzētas kļūdas (500): atbildē un žurnālā nav kļūdas teksta."""

import logging

from fastapi.testclient import TestClient

from app import storage
from app.main import app

SECRET = "32000000101 Līga Ozoliņa sqlite3 db=:memory:"


def test_unexpected_error_hides_exception_text(client, monkeypatch, caplog):
    def broken(submission_id):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(storage, "get", broken)
    caplog.set_level(logging.DEBUG)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/submissions/IES-2026-000001")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "Kļūdas paziņojums"}
    }
    assert "RuntimeError" in caplog.text
    assert SECRET not in caplog.text
