"""CR-A: iedzīvotājs atsauc iesniegumu (POST /submissions/{id}/withdraw)."""

import logging

import pytest

from app import storage

REASON = "Problēma jau ir atrisināta"


def make_submission(client, payload, status="RECEIVED"):
    created = client.post("/submissions", json=payload).json()
    if status != "RECEIVED":
        storage.update_status(created["id"], status)
    return created["id"]


def withdraw(client, submission_id, body):
    return client.post(f"/submissions/{submission_id}/withdraw", json=body)


@pytest.mark.parametrize("status", ["RECEIVED", "IN_PROGRESS"])
def test_withdraw_allowed_status(client, valid_payload, status):
    # 1. un 2. kritērijs
    submission_id = make_submission(client, valid_payload, status)
    due_date = client.get(f"/submissions/{submission_id}").json()["dueDate"]

    response = withdraw(client, submission_id, {"reason": REASON})

    assert response.status_code == 200
    assert response.json()["status"] == "WITHDRAWN"
    # Precizējums: termiņš nemainās
    assert response.json()["dueDate"] == due_date


@pytest.mark.parametrize("status", ["ANSWERED", "WITHDRAWN", "FORWARDED"])
def test_withdraw_not_allowed_status(client, valid_payload, status):
    # 3. un 4. kritērijs; FORWARDED: produkta īpašnieka lēmums 2026-10-05
    submission_id = make_submission(client, valid_payload, status)

    response = withdraw(client, submission_id, {"reason": REASON})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert client.get(f"/submissions/{submission_id}").json()["status"] == status


def test_withdraw_twice_returns_409(client, valid_payload):
    # 4. kritērijs: atkārtota atsaukšana
    submission_id = make_submission(client, valid_payload)
    assert withdraw(client, submission_id, {"reason": REASON}).status_code == 200

    response = withdraw(client, submission_id, {"reason": REASON})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_withdraw_unknown_id_returns_404(client):
    # 5. kritērijs
    response = withdraw(client, "IES-2026-999999", {"reason": REASON})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    ("body", "issue"),
    [
        ({}, "REQUIRED"),
        ({"reason": None}, "INVALID_FORMAT"),
        ({"reason": "a" * 9}, "INVALID_FORMAT"),
        ({"reason": "a" * 501}, "TOO_LONG"),
    ],
)
def test_withdraw_invalid_reason(client, valid_payload, body, issue):
    # 6. kritērijs
    submission_id = make_submission(client, valid_payload)

    response = withdraw(client, submission_id, body)

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"] == [{"field": "reason", "issue": issue}]
    assert client.get(f"/submissions/{submission_id}").json()["status"] == "RECEIVED"


@pytest.mark.parametrize("length", [10, 500])
def test_withdraw_reason_length_boundaries(client, valid_payload, length):
    # 6. kritērijs: robežvērtības ir derīgas
    submission_id = make_submission(client, valid_payload)

    response = withdraw(client, submission_id, {"reason": "a" * length})

    assert response.status_code == 200


def test_withdraw_writes_audit_entry(client, valid_payload):
    # 7. kritērijs
    submission_id = make_submission(client, valid_payload)
    withdraw(client, submission_id, {"reason": REASON})

    audit = client.get(f"/submissions/{submission_id}/audit").json()

    assert audit[-1]["action"] == "WITHDRAW"
    assert audit[-1]["detail"] == REASON


def test_failed_withdraw_writes_no_audit_entry(client, valid_payload):
    submission_id = make_submission(client, valid_payload, "ANSWERED")
    withdraw(client, submission_id, {"reason": REASON})

    audit = client.get(f"/submissions/{submission_id}/audit").json()

    assert [entry["action"] for entry in audit] == ["CREATE"]


def test_withdraw_logs_and_errors_have_no_personal_data(client, valid_payload, caplog):
    # 8. kritērijs
    caplog.set_level(logging.DEBUG)
    submission_id = make_submission(client, valid_payload)
    responses = [
        withdraw(client, submission_id, {"reason": REASON}),
        withdraw(client, submission_id, {"reason": REASON}),
        withdraw(client, submission_id, {"reason": "īss"}),
        withdraw(client, "IES-2026-999999", {"reason": REASON}),
    ]

    sensitive = [
        valid_payload["personalCode"],
        valid_payload["fullName"],
        valid_payload["email"],
        valid_payload["subject"],
        valid_payload["body"],
    ]
    # Iemesls ir auditā, bet ne žurnālā
    assert REASON not in caplog.text
    error_texts = [r.text for r in responses[1:]]
    for value in sensitive:
        assert value not in caplog.text
        for text in error_texts:
            assert value not in text
