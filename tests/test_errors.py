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


def test_error_messages_are_in_latvian(client, valid_payload):
    created = client.post("/submissions", json=valid_payload).json()
    withdraw = f"/submissions/{created['id']}/withdraw"
    reason = {"reason": "Problēma jau ir atrisināta"}
    client.post(withdraw, json=reason)

    cases = [
        (client.post(withdraw, json={}), "Pieprasījumā ir kļūdaini dati"),
        (client.get("/submissions/IES-2026-999999"), "Iesniegums nav atrasts"),
        (client.post(withdraw, json=reason), "Darbība nav atļauta pašreizējā statusā"),
    ]

    for response, message in cases:
        assert response.json()["error"]["message"] == message
