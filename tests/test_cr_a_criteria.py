"""CR-A pieņemšanas kritēriji: viens tests katrai kritēriju rindai.

Sagaidāmās vērtības ņemtas no tracker/CR-A.md un docs/openapi.yaml.
"""

import logging

from app import storage

REASON = "Problēma jau ir atrisināta"
UNKNOWN_ID = "IES-2026-999999"


def _create(client, payload, status="RECEIVED"):
    response = client.post("/submissions", json=payload)
    assert response.status_code == 201
    submission_id = response.json()["id"]
    if status != "RECEIVED":
        storage.update_status(submission_id, status)
    return submission_id


def _withdraw(client, submission_id, body):
    return client.post(f"/submissions/{submission_id}/withdraw", json=body)


def _status(client, submission_id):
    return client.get(f"/submissions/{submission_id}").json()["status"]


def test_cra_ac1_received_withdrawn(client, valid_payload):
    """AC1: Iesniegums ar statusu RECEIVED, iemesls "Problēma jau ir atrisināta"
    -> 200, statuss WITHDRAWN."""
    submission_id = _create(client, valid_payload)
    assert _status(client, submission_id) == "RECEIVED"

    response = _withdraw(client, submission_id, {"reason": REASON})

    assert response.status_code == 200
    assert response.json()["status"] == "WITHDRAWN"


def test_cra_ac2_in_progress_withdrawn(client, valid_payload):
    """AC2: Iesniegums ar statusu IN_PROGRESS, derīgs iemesls
    -> 200, statuss WITHDRAWN."""
    submission_id = _create(client, valid_payload, "IN_PROGRESS")

    response = _withdraw(client, submission_id, {"reason": REASON})

    assert response.status_code == 200
    assert response.json()["status"] == "WITHDRAWN"


def test_cra_ac3_answered_conflict(client, valid_payload):
    """AC3: Iesniegums ar statusu ANSWERED -> 409 INVALID_STATE, statuss nemainās."""
    submission_id = _create(client, valid_payload, "ANSWERED")

    response = _withdraw(client, submission_id, {"reason": REASON})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert _status(client, submission_id) == "ANSWERED"


def test_cra_ac4_repeat_withdraw_conflict(client, valid_payload):
    """AC4: Iesniegums jau ir WITHDRAWN (atkārtota atsaukšana) -> 409 INVALID_STATE."""
    submission_id = _create(client, valid_payload)
    assert _withdraw(client, submission_id, {"reason": REASON}).status_code == 200

    response = _withdraw(client, submission_id, {"reason": REASON})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_cra_ac5_unknown_id_not_found(client):
    """AC5: Nezināms ID -> 404 NOT_FOUND."""
    response = _withdraw(client, UNKNOWN_ID, {"reason": REASON})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_cra_ac6_invalid_reason_validation_error(client, valid_payload):
    """AC6: Nav iemesla, vai iemesls ir īsāks par 10 vai garāks par 500 rakstzīmēm
    -> 400 VALIDATION_ERROR, lauks reason, statuss nemainās."""
    submission_id = _create(client, valid_payload)
    cases = {
        "nav iemesla": {},
        "9 rakstzīmes": {"reason": "a" * 9},
        "501 rakstzīme": {"reason": "a" * 501},
    }

    for name, body in cases.items():
        response = _withdraw(client, submission_id, body)

        assert response.status_code == 400, name
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR", name
        fields = [d["field"] for d in error.get("details", [])]
        assert "reason" in fields, name
        assert _status(client, submission_id) == "RECEIVED", name


def test_cra_ac7_audit_withdraw_entry(client, valid_payload):
    """AC7: Pēc veiksmīgas atsaukšanas GET /submissions/{id}/audit
    -> ir ieraksts ar darbību WITHDRAW, detail ir iemesls."""
    submission_id = _create(client, valid_payload)
    assert _withdraw(client, submission_id, {"reason": REASON}).status_code == 200

    response = client.get(f"/submissions/{submission_id}/audit")

    assert response.status_code == 200
    entries = [e for e in response.json() if e["action"] == "WITHDRAW"]
    assert len(entries) == 1
    assert entries[0]["detail"] == REASON


def test_cra_ac8_no_personal_data_in_logs_or_errors(client, valid_payload, caplog):
    """AC8: Visos gadījumos -> žurnālā (log) un kļūdu atbildēs nav personas koda,
    vārda, e-pasta un iesnieguma teksta."""
    caplog.set_level(logging.DEBUG)
    secrets = [
        valid_payload["personalCode"],
        valid_payload["fullName"],
        valid_payload["email"],
        valid_payload["body"],
    ]

    ok_id = _create(client, valid_payload)
    answered_id = _create(client, valid_payload, "ANSWERED")
    invalid_id = _create(client, valid_payload)

    # Veiksmīga atsaukšana: tikai žurnāls tiek pārbaudīts
    assert _withdraw(client, ok_id, {"reason": REASON}).status_code == 200

    error_responses = [
        _withdraw(client, answered_id, {"reason": REASON}),  # 409
        _withdraw(client, ok_id, {"reason": REASON}),  # 409 atkārtoti
        _withdraw(client, UNKNOWN_ID, {"reason": REASON}),  # 404
        _withdraw(client, invalid_id, {}),  # 400
        _withdraw(client, invalid_id, {"reason": "a" * 9}),  # 400
        _withdraw(client, invalid_id, {"reason": "a" * 501}),  # 400
    ]
    assert sorted(r.status_code for r in error_responses) == [
        400,
        400,
        400,
        404,
        409,
        409,
    ]

    for response in error_responses:
        for secret in secrets:
            assert secret not in response.text, (response.status_code, secret)

    log_text = "\n".join(r.getMessage() for r in caplog.records) + caplog.text
    for secret in secrets:
        assert secret not in log_text, secret
